import argparse
import os
import glob
from Utils.Vam.window import VamWindow
from Utils.Face.normalize import FaceNormalizer
from PIL import Image
from PIL import ImageChops
from PIL import ImageStat
import time
from win32api import GetKeyState
from win32con import VK_CAPITAL, VK_SCROLL
from Utils.Face.encoded import EncodedFace
from Utils.Face.vam import VamFace
import multiprocessing
import queue
import fnmatch
from collections import deque

# Set DPI Awareness  (Windows 10 and 8). Makes GetWindowRect return pxiel coordinates
import ctypes
errorCode = ctypes.windll.shcore.SetProcessDpiAwareness(2)


###############################
# Run the program
#
def main( args ):
    global testJsonPath
    global outputPath
    if args.pydev:
        print("Enabling debugging with pydev")
        import pydevd
        pydevd.settrace(suspend=False)

    inputPath = args.inputJsonPath
    #outputPath = args.outputPath
    outputPath = "-"
    testJsonPath = args.testJsonPath
    numThreads = args.numThreads
    recursive = args.recursive
    fileFilter = args.filter


    print( "Input path: {}\nOutput path: {}\n\n".format( inputPath, outputPath ) )

    # Initialize the Vam window
    vamWindow = VamWindow( idx = args.vamWindow )

    # Locating the buttons via image comparison does not reliably work. These coordinates are the 'Window' coordinates
    # found via AutoHotKey's Window Spy, cooresponding to the Load Preset button and the location of the test file
    vamWindow.setClickLocations([(130,39), (248,178)])

    print("Initializing worker processes...")
    poolWorkQueue = multiprocessing.Queue(maxsize=200)
    doneEvent = multiprocessing.Event()
    if numThreads > 1:
        pool = []
        for idx in range(numThreads):
            proc = multiprocessing.Process(target=worker_process_func, args=(idx, poolWorkQueue, doneEvent, args) )
            proc.start()
            pool.append( proc )
    else:
        pool = None
        doneEvent.set()


    angles = [0, 35]
    skipCnt = 0
    screenshots = deque(maxlen=2)
    for root, subdirs, files in os.walk(inputPath):
        print("Entering directory {}".format(root))
        for file in fnmatch.filter(files, fileFilter):
            try:
                anglesToProcess = [] + angles
                for angle in angles:
                    fileName = "{}_angle{}.png".format( os.path.splitext(file)[0], angle)
                    fileName = os.path.join( root,fileName)
                    if os.path.exists(fileName) or os.path.exists("{}.failed".format(fileName) ):
                        anglesToProcess.remove(angle)

                if len(anglesToProcess) == 0:
                    skipCnt += 1
                    #print("Nothing to do for {}".format(file))
                    continue
                print("Processing {} (after skipping {})".format(file, skipCnt))
                skipCnt = 0

                if (GetKeyState(VK_CAPITAL) or GetKeyState(VK_SCROLL)):
                    print("WARNING: Suspending script due to Caps Lock or Scroll Lock being on. Push CTRL+PAUSE/BREAK or mash CTRL+C to exit script.")
                    while GetKeyState(VK_CAPITAL) or GetKeyState(VK_SCROLL):
                        time.sleep(1)
                # Get screenshots of face and submit them to worker threads
                inputFile = os.path.join( root, file )
                face = VamFace(inputFile)
                for angle in anglesToProcess:
                    face.setRotation(angle)
                    face.save( testJsonPath )
                    vamWindow.loadLook()
                    start = time.time()

                    threshold = 850000000
                    minTime = .3
                    screenshots.append( vamWindow.getScreenShot() )

                    while True:
                        screenshots.append( vamWindow.getScreenShot() )
                        diff = ImageChops.difference( screenshots[0], screenshots[1] )
                        imageStat = ImageStat.Stat( diff )
                        s = sum( imageStat.sum2 )
                        # Todo: Calculate where blue box will be
                        pix = diff.getpixel( (574, 582 ) )
                        if s < threshold and sum(pix) < 50 and time.time() - start >= minTime:
                            break
                        #print( "{} < {}: {}, {} {}".format(s, threshold, s < threshold, pix, sum(pix) ) )
                    outputFileName = "{}_angle{}.png".format( os.path.splitext(os.path.basename(inputFile))[0], angle)
                    outputFileName = os.path.join( root, outputFileName )
                    poolWorkQueue.put( ( screenshots.pop(), outputFileName))

                    if pool is None:
                        worker_process_func(0, poolWorkQueue, doneEvent, args)
            except Exception as e:
                print("Failed to process {} - {}".format(file, str(e)))

        if not recursive:
            break

    print("Generator done!")
    doneEvent.set()
    if pool:
        for proc in pool:
            proc.join()

###############################
# Worker function for helper processes
###############################
def worker_process_func(procId, workQueue, doneEvent, args):
    print("Worker {} started".format(procId))
    normalizer = FaceNormalizer(args.normalizeSize)

    while not ( doneEvent.is_set() and workQueue.empty() ):
        try:
            work = workQueue.get(block=True, timeout=1)
            image = work[0]
            outputFile = work[1]
            #print("Worker thread {} to generate {}".format(procId, outputFile))

            try:
                image = normalizer.normalize(image)
                image.save( outputFile )
                print("Worker thread {} generated {}".format(procId, outputFile))
            except:
                print("Worker {} Failed to generate {}".format(procId, outputFile))
                open( "{}.failed".format(outputFile), 'w' )
                #image.save( "{}.failed.png".format(outputFile) )
        except queue.Empty:
            pass
    print("Worker {} done!".format(procId))



###############################
# parse arguments
#
def parseArgs():
    parser = argparse.ArgumentParser( description="Generate images for json" )
    parser.add_argument('--inputJsonPath', help="Directory containing json files to start with", required=True)
    parser.add_argument('--filter', help="File filter to process. Defaults to *.json", default="*.json")
    parser.add_argument('--normalizeSize', type=int, help="Size of normalized output. Defaults to 500", default=500)
    #parser.add_argument('--outputPath', help="Directory to write output data to", default="output")
    parser.add_argument('--testJsonPath', help="Directory where test JSON will be stored", default="test")
    parser.add_argument("--numThreads", type=int, default=1, help="Number of processes to use")
    parser.add_argument("--vamWindow", type=int, default=0, help="Index of VaM window to use")
    parser.add_argument("--pydev", action='store_true', default=False, help="Enable pydevd debugging")
    parser.add_argument("--recursive", action='store_true', default=False, help="Recursively enter directories")
    return parser.parse_args()

###############################
# program entry point
#
if __name__ == "__main__":
    args = parseArgs()
    main( args )