Python Scripts to initialize and park the Wave150i mount via Wifi or USB.
In a way similar to SynScan Pro, the script move the motors to the park position, 
whatever the initial position is.
The initialization sequence is sent prior to any motion.
SynScanPro(c) Skywatcher set the encoder values to default values that are different from those
expected by some drivers (e.g. INDI/ekos)
The script allows also to change this origin value.
