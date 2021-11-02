# relion-external-jobs

Python scripts for Relion 4 "External job" type

## Preparation

Before running the scripts you will need to:

1. install emtable - the STAR file parser: `pip3 install --user emtable`
2. edit the variables inside the scripts so that they point to a correct conda environments and training models
3. make the scripts executable and provide full path to them in Relion GUI
4. run scripts from Relion project directory

To see all available arguments, use for example: **./external_job_cryolo.py -h**

## Examples

### Single particle picking with Cryolo

From command line run: 
```
./external_job_cryolo.py --in_mics MotionCorr/job002/corrected_micrographs.star --o picking --gpu 0,1 
```

Alternatively, from Relion GUI:

![image](https://user-images.githubusercontent.com/6952870/139669068-6b55d83b-04f6-4181-8d54-7de17bb04bb5.png)
![image](https://user-images.githubusercontent.com/6952870/139669190-a36f04c8-078e-4b37-9883-fd7580421c98.png)

### Helical picking with Cryolo:

From command line run:: 
```
./external_job_cryolo.py --in_mics MotionCorr/job002/corrected_micrographs.star --o picking --model cryolo_model.h5 --box_size 140 --filament --bd 40 --mn 1
```

Alternatively, from Relion GUI:

![image](https://user-images.githubusercontent.com/6952870/139668687-008e171d-055e-456e-af3a-5ac3522cd872.png)
![image](https://user-images.githubusercontent.com/6952870/139843254-a050294a-785f-4f7d-bf89-b4ff252c6308.png)
