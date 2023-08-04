#!/usr/bin/env python3
# **************************************************************************
# *
# * Authors:     Grigory Sharov (gsharov@mrc-lmb.cam.ac.uk) [1]
# *
# * [1] MRC Laboratory of Molecular Biology, MRC-LMB
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 3 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'gsharov@mrc-lmb.cam.ac.uk'
# *
# **************************************************************************
""" Based on https://github.com/DiamondLightSource/python-relion-yolo-it by
Sjors H.W. Scheres, Takanori Nakane, Colin M. Palmer, Donovan Webb"""

import argparse
import json
import os
import time
import subprocess
from emtable import Table  # run "pip3 install --user emtable" for system python


CONDA_ENV = ". /lmb/home/gsharov/rc/conda.rc && module load cuda/11.6 && conda activate cryolo-1.9.3"
CRYOLO_TRAIN = "cryolo_train.py"
CRYOLO_GEN_MODEL = "/public/EM/Scipion/scipion-dev/software/em/cryolo_model-202005_N63_c17/gmodel_phosnet_202005_N63_c17.h5"
CRYOLO_JANNI_MODEL = "/public/EM/Scipion/scipion-dev/software/em/janni_model-20190703/gmodel_janni_20190703.h5"
TUNE_MODEL = "fine_tuned_model.h5"
IMG_FOLDER = "train_image"
ANNOT_FOLDER = "train_annot"
SCRATCH_DIR = os.getenv("RELION_SCRATCH_DIR", None)  # SSD scratch space for filtered mics, can be None
DEBUG = 0


def run_job(project_dir, args):
    start = time.time()
    in_parts = args.in_parts
    job_dir = args.out_dir
    model = args.model or CRYOLO_GEN_MODEL
    gpus = args.gpu
    nmics = args.n

    getPath = lambda *arglist: os.path.join(project_dir, *arglist)

    if SCRATCH_DIR is not None:
        filtered_dir = os.path.join(SCRATCH_DIR, "filtered_tmp")
    else:
        filtered_dir = "%s/filtered_tmp/" % job_dir

    # Create folder structure for cryolo
    os.mkdir(IMG_FOLDER)
    os.mkdir(ANNOT_FOLDER)

    # Reading the box size from relion
    optics = Table(fileName=getPath(in_parts), tableName='optics')[0]
    box_bin = int(optics.rlnImageSize)
    box_size = float(optics.rlnImagePixelSize) // float(optics.rlnMicrographOriginalPixelSize) * box_bin
    print("Using unbinned box size of %d px" % box_size)

    # Making a cryolo config file
    json_dict = {
        "model": {
            "architecture": "PhosaurusNet",
            "input_size": 1024,
            "max_box_per_image": 600,
            "anchors": [box_size, box_size],
            "filter": [
                0.1,
                filtered_dir
            ]
        },
        "train": {
            "train_image_folder": IMG_FOLDER,
            "train_annot_folder": ANNOT_FOLDER,
            "train_times": 10,
            "batch_size": 6,
            "learning_rate": 0.0001,
            "nb_epoch": 200,
            "object_scale": 5.0,
            "no_object_scale": 1.0,
            "coord_scale": 1.0,
            "class_scale": 1.0,
            "pretrained_weights": "%s" % model,
            "saved_weights_name": getPath(job_dir, TUNE_MODEL),
            "debug": True
        },
        "valid": {
            "valid_image_folder": "",
            "valid_annot_folder": "",
            "valid_times": 1
        }
    }

    if DEBUG:
        print("Using following config: ", json_dict)

    with open("config_cryolo.json", "w") as json_file:
        json.dump(json_dict, json_file, indent=4)

    # Reading the particles from relion
    try:
        parttable = Table(fileName=getPath(in_parts), tableName='particles')
    except:
        print("Could not read particles table from %s. Stopping" % in_parts)
        return

    # Arranging files for cryolo: making symlinks for mics and creating star files
    mics_dict = {}
    for row in parttable:
        mic = row.rlnMicrographName
        if mic in mics_dict:
            mics_dict[mic].append((row.rlnCoordinateX, row.rlnCoordinateY))
        else:
            mics_dict[mic] = [(row.rlnCoordinateX, row.rlnCoordinateY)]

    mics_dict = dict(sorted(mics_dict.items(), key=lambda item: -1*len(item[1])))
    for mic_num, mic in enumerate(mics_dict):
        if 0 < nmics <= mic_num:
            break
        micSrc = getPath(mic)
        micDst = getPath(job_dir, IMG_FOLDER, os.path.basename(mic))
        if not os.path.exists(micDst):
            os.symlink(micSrc, micDst)
        if DEBUG:
            print("Link %s --> %s" % (micSrc, micDst))

        coordFn = os.path.splitext(micDst)[0] + ".star"
        coordFn = coordFn.replace(IMG_FOLDER, ANNOT_FOLDER)
        with open(coordFn, "w") as fn:
            table_coords = Table(columns=['rlnCoordinateX', 'rlnCoordinateY'])
            for coord in mics_dict[mic]:
                table_coords.addRow(coord[0], coord[1])
            table_coords.writeStar(fn, tableName='')
        if DEBUG:
            print("Created coord star file: %s" % coordFn)

    # Launching cryolo
    args_dict = {
        '--conf': "config_cryolo.json",
        '--gpu': gpus.replace(',', ' '),
        '--warmup': 0,
        '--fine_tune': "",
        '--cleanup': ""
    }
    cmd = "%s && %s " % (CONDA_ENV, CRYOLO_TRAIN)
    cmd += " ".join(['%s %s' % (k, v) for k, v in args_dict.items()])

    print("Running command:\n{}".format(cmd))
    proc = subprocess.Popen(cmd, shell=True)
    proc.communicate()

    if proc.returncode:
        raise Exception("Command failed with return code %d" % proc.returncode)

    # Required output job_pipeline.star file
    pipeline_fn = getPath(job_dir, "job_pipeline.star")
    table_gen = Table(columns=['rlnPipeLineJobCounter'])
    table_gen.addRow(2)
    table_proc = Table(columns=['rlnPipeLineProcessName', 'rlnPipeLineProcessAlias',
                                'rlnPipeLineProcessTypeLabel', 'rlnPipeLineProcessStatusLabel'])
    table_proc.addRow(job_dir, 'None', 'relion.external', 'Running')
    table_nodes = Table(columns=['rlnPipeLineNodeName', 'rlnPipeLineNodeTypeLabel'])
    table_nodes.addRow(in_parts, "ParticlesData.star.relion")
    table_input = Table(columns=['rlnPipeLineEdgeFromNode', 'rlnPipeLineEdgeProcess'])
    table_input.addRow(in_parts, job_dir)

    with open(pipeline_fn, "w") as f:
        table_gen.writeStar(f, tableName="pipeline_general", singleRow=True)
        table_proc.writeStar(f, tableName="pipeline_processes")
        table_nodes.writeStar(f, tableName="pipeline_nodes")
        table_input.writeStar(f, tableName="pipeline_input_edges")

    end = time.time()
    diff = end - start
    print("Job duration = %dh %dmin %dsec \n" % (diff // 3600, diff // 60 % 60, diff % 60))


def main():
    """Change to the job working directory, then call run_job()"""
    help = """
External job for calling crYOLO fine-tune training within Relion 4.0. Run it in the Relion project directory, e.g.:
    external_job_cryolo_train.py --o External/cryolo_training --in_parts Select/job004/particles.star --n 20
"""
    parser = argparse.ArgumentParser(usage=help)
    parser.add_argument("--in_parts", help="Input particles STAR file")
    parser.add_argument("--o", dest="out_dir", help="Output directory name")
    parser.add_argument("--model", help="Cryolo training model (if not specified general is used)")
    parser.add_argument("--gpu", help='GPUs to use (e.g. "0,1,2,3")', default="0")
    parser.add_argument("--n", help='Select only N most populated micrographs (default=20)', type=int, default=20)
    parser.add_argument("--j", dest="threads", help="Not used here. Required by Relion")
    parser.add_argument("--pipeline_control", help="Not used here. Required by Relion")

    args = parser.parse_args()

    if args.in_parts is None or args.out_dir is None:
        print("Error: --in_parts and --o are required params!")
        exit(1)

    if not args.in_parts.endswith(".star"):
        print("Error: --in_parts must point to a particles star file")
        exit(1)

    project_dir = os.getcwd()
    os.makedirs(args.out_dir, exist_ok=True)
    RELION_JOB_FAILURE_FILENAME = "RELION_JOB_EXIT_FAILURE"
    RELION_JOB_SUCCESS_FILENAME = "RELION_JOB_EXIT_SUCCESS"

    os.chdir(args.out_dir)
    if os.path.isfile(RELION_JOB_FAILURE_FILENAME):
        os.remove(RELION_JOB_FAILURE_FILENAME)
    if os.path.isfile(RELION_JOB_SUCCESS_FILENAME):
        os.remove(RELION_JOB_SUCCESS_FILENAME)
    try:
        run_job(project_dir, args)
    except:
        open(RELION_JOB_FAILURE_FILENAME, "w").close()
        raise
    else:
        open(RELION_JOB_SUCCESS_FILENAME, "w").close()


if __name__ == "__main__":
    main()
