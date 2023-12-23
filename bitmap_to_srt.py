#!/bin/bash/python
import numpy as np
import cv2 as cv
import os
import sys
import tempfile
import argparse
from PIL import Image
import pytesseract

#custom_config = r'--psm 6 -c tessedit_char_whitelist= 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz?,!.|'
verbose = False

def seconds_to_time_format(seconds):
    # Calculate hours, minutes, and remaining seconds
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    # Calculate milliseconds (rounded to 3 decimal places)
    milliseconds = int((seconds - int(seconds)) * 1000)
    time_format = "{:02d}:{:02d}:{:02d},{:03d}".format(int(hours), int(minutes), int(seconds), milliseconds)
    return time_format

def get_num_subtitle_streams(video_file):
    process = os.popen('ffprobe -loglevel error -select_streams s -show_entries stream=index -of csv=p=0 "{}"'.format(video_file))
    num_of_subtitles = process.read().count('\n')
    return num_of_subtitles

def get_duration(file_path):
    process = os.popen('ffprobe -i "{}" -show_entries format=duration -v quiet -of csv="p=0"'.format(file_path))
    duration = process.read().strip()
    process.close()
    return duration

def image_to_text_stripped(image):
    return pytesseract.image_to_string(image).strip().replace("|", "I").replace('”', '"')

#Returns an absolute pathname to the temporary file
def create_temporary_file():
    t = tempfile.mkstemp(suffix = ".mkv")
    os.close(t[0]) #closes the os file descriptor, file exists and is closed
    #t = ("", "what.mkv")
    return t[1]

#Used to create video with a black background with just subtitles on it at a given frame rate
#default 10
#returns the absolute path to the newly created video
def generate_subtitle_video(file_path, fps, temp_file_path, subtitle_stream = 0):
    duration = get_duration(file_path)
    cmd = 'ffmpeg -i "{}" -f lavfi -i "color=size=1920x1080:rate={}:color=black@0.0" -filter_complex "[1:v][0:s:{}]overlay" -an -y -to {} "{}" 2> /dev/null'.format(file_path, fps, subtitle_stream, duration, temp_file_path)
    process = os.popen(cmd)
    process.close()

class SubtitleInfoGenerator:
    def __init__(self, video_path, fps):
        self._video_capture = cv.VideoCapture(video_path)
        self._current_frame = None
        self._frame_number = -1
        self._fps = fps #needed to generate time stamps
    def _areImagesSame(self, frame):
        if type(self._current_frame) == type(None):
            return False
        #current_frame_hist = cv.calcHist([self._current_frame], [0], None, [256], [0, 256])
        #next_frame_hist = cv.calcHist([frame], [0], None, [256], [0, 256])
        #correlation_percent = cv.compareHist(current_frame_hist, next_frame_hist, cv.HISTCMP_CORREL)
        #1 for perfect match, 0 for no correlation, -1 for one being the negative of the other
        #print(correlation_percent)
        #if correlation_percent > 0.9999999:
        #    return True
        #else:
            
         #   cv.imshow("", frame)
         #   cv.waitKey()
         #   return False
        if np.array_equal(self._current_frame, frame):
            return True
        else:
            return False
         
    #Throws a StopIteration when finished
    def _continue_until_changed(self):
        while True:
            valid, next_frame = self._video_capture.read()
            if not valid:
                raise StopIteration()
            else:
                next_frame = cv.cvtColor(next_frame, cv.COLOR_BGR2GRAY) #Converts to greyscale, may not be needed
                self._frame_number += 1

            if not self._areImagesSame(next_frame):
                self._current_frame = next_frame
                return
            
            
    
    
    #Returns a tuple, start time, end time, and text
    def get_next_subtitle(self):
        if type(self._current_frame) == type(None): #handles special case of beginning over
            self._continue_until_changed()
        #if current frame has text, get it otherwise continue searching until text is found or video ends
        frame_text = image_to_text_stripped(self._current_frame)
        while frame_text == "":
            self._continue_until_changed()
            frame_text = image_to_text_stripped(Image.fromarray(self._current_frame))
        start_time = self._frame_number / self._fps
        try: #finds end of the subtitle, if frames end before found end, then the end time is the end of the video
            self._continue_until_changed()
            #If text not changed, keep looking to find the end of the subtitle
            debug_str = image_to_text_stripped(self._current_frame)
            #print(debug_str, frame_text, debug_str == frame_text)
            while debug_str == frame_text:
                self._continue_until_changed()
                debug_str = image_to_text_stripped(self._current_frame)
        except StopIteration: 
             pass
        end_time = self._frame_number / self._fps
        return (start_time, end_time, frame_text)

    def __iter__(self):
        return self
    
    def __next__(self):
        return self.get_next_subtitle()
    
        
            
            
        
#Returns a list of tuples in the form of (start_time, end_time, subtitle_text)
def generateSubtitlesList(subtitle_video, fps):
    generator = SubtitleInfoGenerator(subtitle_video, fps)
    generated_list = []
    for tup in generator:
        generated_list.append(tup)

    return generated_list
    
def createSrtFile(srt_filename, subtitle_list):
    srt_file = open(srt_filename, "w+")
    subtitle_number = 1
    for subtitle_info in subtitle_list:
        srt_file.write("{}\n{} --> {}\n{}\n\n".format(subtitle_number, seconds_to_time_format(subtitle_info[0]), seconds_to_time_format(subtitle_info[1]), subtitle_info[2]))
        subtitle_number += 1
    
    srt_file.close()
    

def main(args):
    FPS = 10
    verbose = args['v']
    stream_number = int(args['s'])
    number_of_sub_streams_in_video = get_num_subtitle_streams(args['input_filename'])
    if number_of_sub_streams_in_video < 1:
        print("Error: input_file has no subtitle streams.")
        sys.exit(-1)
    elif stream_number < 0:
        print('Error: Stream number must be at least 0.')
        sys.exit(-2)
    elif stream_number > number_of_sub_streams_in_video:
        print('Error: Specified stream {} not in {} (has {} subtitle streams)'.format(stream_number, args['input_filename'], number_of_sub_streams_in_video))
        sys.exit(-3)
        
    try:
        temp_file_path = create_temporary_file()
        if verbose: print("Preprocessing video")
        generate_subtitle_video(args["input_filename"], FPS, temp_file_path)
        if verbose: print("Extracting subtitles")
        subtitle_list = generateSubtitlesList(temp_file_path, FPS)
        createSrtFile(args["o"], subtitle_list)
        if verbose: print("Wrote srt file to " + args["o"])
    except KeyboardInterrupt:
        print("KeyBoardInterrupt")
    except Exception:
        raise Exception("An exception occurred!")
    finally:
        os.unlink(temp_file_path)
    
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="This program gets a given video file's specified subtitle track and converts it into an srt file.")
    parser.add_argument("input_filename", help="the video file to process")    
    parser.add_argument("-o", required = False, default = 'subtitle.srt', help = "the srt file to create")
    parser.add_argument("-s", nargs = "?", default = 0, help = "the subtitle track to convert to an srt file. Defaults to the first subtitle stream")
    parser.add_argument("-v", action='store_true', help = "specifies if verbose output is wanted") 
    main(vars(parser.parse_args()))
    
    


