#!/usr/bin/env python3
"""
Creates a montage grid of frames from a video file with frame and
time offset labels to help give a basic summary of the video file
contents.
"""

import argparse
import os
import tempfile
import shutil  # Add this import for copying files
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

    parser.add_argument(
        dest="input_file",
        nargs=1,
        help="Input video file (any ffmpeg compatible format)",
    )

    parser.add_argument(dest="output_file", nargs=1, help="Output file")

    parser.add_argument(
        "-c",
        "--cols",
        default=DEFAULT_COLS,
        type=int,
        help=f"How many columns of frames (default {DEFAULT_COLS})",
    )

    parser.add_argument(
        "-r",
        "--rows",
        default=DEFAULT_ROWS,
        type=int,
        help=f"How many rows of frames (default {DEFAULT_ROWS})",
    )

    parser.add_argument(
        "-nl",
        "--no-labels",
        action="store_true",
        help="Disable rendering of frame labels",
    )

    parser.add_argument(
        "--keep-frames",
        type=str,
        help="Directory to save extracted frames. If not specified, frames are deleted after montage creation.",
    )

    args = parser.parse_args()

    doIt()


def doIt():
    try:
        # Create a temporary directory for intermediate files
        with tempfile.TemporaryDirectory() as temp_dir:
            source_video_filename = os.path.abspath(args.input_file[0])
            source_video_filename_quoted = f'"{source_video_filename}"'

            # Query ffprobe for the frame count
            h = os.popen(CMD_FFPROBE_FRAME_COUNT + source_video_filename_quoted)
            vid_frames_total = int(h.read().strip().strip(","))

            # Query ffprobe for the framerate
            h2 = os.popen(CMD_FFPROBE_FRAMERATE_COUNT + source_video_filename_quoted)
            vid_fps = round(eval(h2.read().strip().strip(",")), 3)

            # Get an estimate of how long the video is, in minutes
            vid_minutes = round((vid_frames_total / vid_fps) / 60, 3)
            grid_total_frames = args.cols * args.rows

            print(
                f"* There are {vid_frames_total} frames at {vid_fps}fps for ~{vid_minutes} mins."
            )

            print(
                f"* Grid of size {args.cols}x{args.rows} will have {grid_total_frames} frames."
            )

            frame_index_roster = []
            select_elements = []
            frame_data = []
            label_fnames = []
            extracted_frame_ids = []  # Track which frames are actually extracted

            # gather a list of candidate frame numbers to extract
            for grid_frame_index in range(args.cols * args.rows):
                frame_index = (
                    round(vid_frames_total / grid_total_frames) * grid_frame_index
                    + INTERFRAME_OFFSET
                )
                if frame_index < vid_frames_total:
                    frame_index_roster.append(frame_index)
                    extracted_frame_ids.append(grid_frame_index)  # Only valid indices

            # builds list of frame index specifiers to pass to ffmpeg, also sets up later vars
            i = 1
            for grid_frame_index in extracted_frame_ids:
                frame_index = frame_index_roster[grid_frame_index]
                top = "eq(n\\,"
                bot = top + f"{frame_index})"
                select_elements.append(bot)

                pct_done = frame_index / vid_frames_total
                min_offs = vid_minutes * pct_done

                label_text = f"Frame {frame_index} @ {round(min_offs,2)} min ({round(pct_done * 100,2)}%)"
                frame_data.append(label_text)

                if args.no_labels:
                    label_fnames.append(os.path.join(temp_dir, f"frame_{i}.png"))
                else:
                    label_fnames.append(os.path.join(temp_dir, f"labeled_{i}.png"))
                i += 1

            # Determine the directory for saving frames
            frame_save_dir = args.keep_frames if args.keep_frames else temp_dir

            # Ensure the directory exists if --keep-frames is specified
            if args.keep_frames and not os.path.exists(frame_save_dir):
                os.makedirs(frame_save_dir)

            # Build the ffmpeg extraction call for original-sized frames
            cmd_extract_original = f"ffmpeg -hide_banner -loglevel error -i {source_video_filename_quoted} "
            cmd_extract_original += f" -vf \"select='{'+'.join(select_elements)}'\" -vsync 0 {os.path.join(temp_dir, 'original_frame_%d.png')}"

            print("* Extracting original-sized frames...")
            if os.system(cmd_extract_original):
                os._exit(-1)

            # Copy original-sized frames to the --keep-frames directory if specified
            if args.keep_frames:
                print(f"* Copying original-sized frames to `{args.keep_frames}`...")
                if not os.path.exists(args.keep_frames):
                    os.makedirs(args.keep_frames)
                for frame_id in range(len(extracted_frame_ids)):
                    src_original = os.path.join(
                        temp_dir, f"original_frame_{1+frame_id}.png"
                    )
                    dest_original = os.path.join(
                        args.keep_frames, f"original_frame_{1+frame_id}.png"
                    )
                    shutil.copy(src_original, dest_original)

            # Build the ffmpeg extraction call for resized frames
            vfsel = f"-vf \"select='{'+'.join(select_elements)}', scale={EXTRACTED_FRAME_WIDTH}\:-1, {FFMPEG_SHARP}\""
            cmd_extract_resized = f"ffmpeg -hide_banner -loglevel error -i {source_video_filename_quoted} {vfsel} "
            cmd_extract_resized += f" -vsync 0 {os.path.join(temp_dir, 'frame_%d.png')}"

            print("* Extracting resized frames...")
            if os.system(cmd_extract_resized):
                os._exit(-1)

            # Add labels to all the resized frames
            if not args.no_labels:
                print("* Building labeled versions...")
                for frame_id in range(len(extracted_frame_ids)):
                    cmd_label = f'convert {os.path.join(temp_dir, f"frame_{1+frame_id}.png")} -background black -fill white -pointsize {LABEL_FONTSIZE} label:"{frame_data[frame_id]}" -gravity center -append {os.path.join(temp_dir, f"labeled_{1+frame_id}.png")}'
                    if os.system(cmd_label):
                        os._exit(-1)

            print(f"* Building montage to `{args.output_file[0]}`...")

            cmd_montage = f"montage -density {EXTRACTED_FRAME_WIDTH} -tile {args.cols}x{args.rows} -geometry +0+0 -border 0 "
            cmd_montage += " ".join(label_fnames)
            cmd_montage += f' "{args.output_file[0]}"'

            if os.system(cmd_montage):
                os._exit(-1)

    except Exception as e:
        print("Some horrible thing happened: ")
        print(e)

    finally:
        # Remove temporary files
        print("* Removing temporary files...")
        for frame_id in range(len(extracted_frame_ids)):
            f = os.path.join(temp_dir, f"frame_{1+frame_id}.png")
            if exists(f):
                os.remove(f)

            f = os.path.join(temp_dir, f"original_frame_{1+frame_id}.png")
            if exists(f):
                os.remove(f)

            if not args.no_labels:
                f = os.path.join(temp_dir, f"labeled_{1+frame_id}.png")
                if exists(f):
                    os.remove(f)


if __name__ == "__main__":
    main()
