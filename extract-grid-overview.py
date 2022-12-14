#!/usr/bin/env python3
'''
Creates a montage grid of frames from a video file with frame and
time offset labels to help give a basic summary of the video file
contents.
'''

import argparse
import os
from os.path import exists

CMD_FFPROBE_FRAME_COUNT = "ffprobe -v error -select_streams v:0 -count_packets -show_entries stream=nb_read_packets -of csv=p=0 "
CMD_FFPROBE_FRAMERATE_COUNT = "ffprobe -v error -select_streams v:0 -of default=noprint_wrappers=1:nokey=1 -show_entries stream=r_frame_rate "
FFMPEG_SHARP = "unsharp=lx=5:ly=5:la=0.5"

DEFAULT_COLS = 8
DEFAULT_ROWS = 8
INTERFRAME_OFFSET = 30  # used to avoid the "black frame 0" problem


# too big and `montage` will run out of memory -- yes, it seems to load each frame into memory when building... 8x8x1920x1080x4
EXTRACTED_FRAME_WIDTH = 256

LABEL_FONTSIZE = 10

args = None


def main():
    global args

    # todo - verify existence of support tools

    parser = argparse.ArgumentParser()

    parser.add_argument(dest="input_file", nargs=1,
                        help="Input video file (any ffmpeg compatible format)")

    parser.add_argument(dest="output_file", nargs=1,
                        help="Output file")

    parser.add_argument('-c', '--cols', default=DEFAULT_COLS, type=int,
                        help=f"How many columns of frames (default {DEFAULT_COLS})")

    parser.add_argument('-r', '--rows', default=DEFAULT_ROWS,  type=int,
                        help=f"How many rows of frames (default {DEFAULT_ROWS})")

    parser.add_argument('-nl', '--no-labels', action='store_true',
                        help="Disable rendering of frame labels")

    args = parser.parse_args()

    doIt()


def doIt():
    try:
        source_video_filename = os.path.abspath(args.input_file[0])
        source_video_filename_quoted = f"\"{source_video_filename}\""

        # Query ffprobe for the frame count
        h = os.popen(CMD_FFPROBE_FRAME_COUNT + source_video_filename_quoted)
        vid_frames_total = int(h.read().strip())

        # Query ffprobe for the framerate
        h2 = os.popen(CMD_FFPROBE_FRAMERATE_COUNT + source_video_filename_quoted)
        vid_fps = round(eval(h2.read().strip()), 3)

        # Get an estimate of how long the video is, in minutes
        vid_minutes = round((vid_frames_total / vid_fps)/60, 3)
        grid_total_frames = args.cols * args.rows

        print(
            f"* There are {vid_frames_total} frames at {vid_fps}fps for ~{vid_minutes} mins.")

        print(
            f"* Grid of size {args.cols}x{args.rows} will have {grid_total_frames} frames.")

        frame_index_roster = []  # array of frame indexes into the video
        select_elements = []     # array for building the ffmpeg extraction call
        frame_data = []          # array holding the label under each frame
        label_fnames = []        # filenames for the resulting labeled frames

        # gather a list of candidate frame numbers to extract
        for grid_frame_index in range(args.cols * args.rows):
            frame_index_roster.append(
                round(vid_frames_total / grid_total_frames) * grid_frame_index + INTERFRAME_OFFSET)

        # builds list of frame index specifiers to pass to ffmpeg, also sets up later vars
        i = 1
        for row in range(args.rows):
            for col in range(args.cols):
                frame_index = frame_index_roster[args.cols * row + col]
                top = "eq(n\\,"
                bot = top + f"{frame_index})"
                select_elements.append(bot)

                pct_done = (frame_index / vid_frames_total)
                min_offs = vid_minutes * pct_done

                label_text = f"Frame {frame_index} @ {round(min_offs,2)} min ({round(pct_done * 100,2)}%)"
                frame_data.append(label_text)

                if args.no_labels:
                    label_fnames.append(f"montage_frame_{i}.png")
                else:
                    label_fnames.append(f"montage_labeled_{i}.png")
                i += 1

        # build the ffmpeg extraction call
        vfsel = f"-vf \"select='{'+'.join(select_elements)}', scale={EXTRACTED_FRAME_WIDTH}\:-1, {FFMPEG_SHARP}\""
        cmd_extract = f"ffmpeg -hide_banner -loglevel error -i {source_video_filename_quoted} {vfsel} "
        cmd_extract += f" -vsync 0 montage_frame_%d.png"

        print("* Extracting frames (this will take some time depending on size of grid)...")

        if os.system(cmd_extract):
            os._exit(-1)

        # add labels to all the exported frames
        if not args.no_labels:
            print("* Building labeled versions...")
            for frame_id in range(args.cols * args.rows):
                cmd_label = f"convert montage_frame_{1+frame_id}.png -background black -fill white -pointsize {LABEL_FONTSIZE} label:\"{frame_data[frame_id]}\" -gravity center -append montage_labeled_{1+frame_id}.png"
                # print(frame_data[frame_id])
                if os.system(cmd_label):
                    os._exit(-1)

        print(f"* Building montage to `{args.output_file[0]}`...")

        cmd_montage = f"montage -density {EXTRACTED_FRAME_WIDTH} -tile {args.cols}x{args.rows} -geometry +0+0 -border 0 "
        cmd_montage += " ".join(label_fnames)
        cmd_montage += f" {args.output_file[0]}"

        if os.system(cmd_montage):
            os._exit(-1)

    except Exception as e:
        print("Some horrible thing happened: ")
        print(e)

    finally:
        # try to delete all our temporary files
        print("* Removing temporary files...")
        for i in range(args.cols * args.rows):
            f = f"montage_frame_{1+i}.png"
            if exists(f):
                os.remove(f)

            if not args.no_labels:
                f = f"montage_labeled_{1+i}.png"
                if exists(f):
                    os.remove(f)


if __name__ == "__main__":
    main()
