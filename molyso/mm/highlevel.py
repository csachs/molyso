# -*- coding: utf-8 -*-
"""
documentation
"""

from __future__ import division, unicode_literals, print_function

__citation__ = "molyso: A software for mother machine analysis, working title. Sachs et al."

import argparse
import sys
import os
import numpy
import itertools
import codecs
import json
import multiprocessing

from .. import Debug, TunableManager

from ..generic.etc import parse_range, correct_windows_signal_handlers, debug_init, QuickTableDumper, \
    silent_progress_bar, fancy_progress_bar

from ..imageio.imagestack import MultiImageStack
from ..imageio.imagestack_ometiff import OMETiffStack
from .image import Image
from .fluorescence import FluorescentImage

from .tracking import TrackedPosition, analyze_tracking, plot_timeline, tracker_to_cell_list

OMETiffStack = OMETiffStack

def banner():
    return """
      \   /\  /\  /                             -------------------------
       | | |O| | |    molyso                    Developed  2013 - 2014 by
       | | | | |O|                              Christian   C.  Sachs  at
       |O| |O| |O|    MOther    machine         Microscale Bioengineering
       \_/ \_/ \_/    anaLYsis SOftware         Research  Center  Juelich
     --------------------------------------------------------------------
     If you use this software in a publication, please cite our paper:

     %(citation)s
     --------------------------------------------------------------------
    """ % {"citation": __citation__}


def create_argparser():
    argparser = argparse.ArgumentParser(description="molyso: MOther machine anaLYsis SOftware")

    def _error(message=""):
        print(banner())
        argparser.print_help()
        sys.stderr.write("%serror: %s%s" % (os.linesep, message, os.linesep,))
        sys.exit(1)

    argparser.error = _error

    argparser.add_argument('input', metavar='input', type=str, help="input file")
    argparser.add_argument('-tp', '--timepoints', dest='timepoints', default=[0, float('inf')], type=parse_range)
    argparser.add_argument('-mp', '--multipoints', dest='multipoints', default=[0, float('inf')], type=parse_range)
    argparser.add_argument('-o', '--table-output', dest='table_output', type=str, default=None)
    argparser.add_argument('-ot', '--output-tracking', dest='tracking_output', type=str, default=None)
    argparser.add_argument('-nb', '--no-banner', dest='nb', default=False, action='store_true')
    argparser.add_argument('-cpu', '--cpus', dest='mp', default=-1, type=int)
    argparser.add_argument('-debug', '--debug', dest='debug', default=False, action='store_true')
    argparser.add_argument('-q', '--quiet', dest='quiet', default=False, action='store_true')
    argparser.add_argument('-nc', '--no-cache', dest='nocache', default=False, action='store_true')
    argparser.add_argument('-rt', '--read-tunables', dest='read_tunables', type=str, default=None)
    argparser.add_argument('-wt', '--write-tunables', dest='write_tunables', type=str, default=None)
    argparser.add_argument('-zm', '--z-is-multipoint', dest='zm', default=False, action='store_true')

    return argparser


def setup_image(i, local_ims, t, pos):
    img = local_ims.get_image(t=t, pos=pos, channel=local_ims.__class__.Phase_Contrast, float=True)

    i.setup_image(img)

    if local_ims.get_meta('channels') > 1:
        fimg = local_ims.get_image(t=t, pos=pos, channel=local_ims.__class__.Fluorescence, float=True)

        i.setup_fluorescence(fimg)

    i.multipoint = int(pos)
    i.timepoint_num = int(t)

    i.timepoint = local_ims.get_meta('time', t=t, pos=pos)

    i.calibration_px_to_mu = local_ims.get_meta('calibration', t=t, pos=pos)

    i.metadata['x'], i.metadata['y'], i.metadata['z'] = local_ims.get_meta('position', t=t, pos=pos)

    i.metadata['time'] = i.timepoint
    i.metadata['timepoint'] = i.timepoint_num
    i.metadata['multipoint'] = i.multipoint

    i.metadata['calibration_px_to_mu'] = i.calibration_px_to_mu

    i.metadata['tag'] = ''
    i.metadata['tag_number'] = 0


# globals

ims = None


def processing_frame(t, pos):
    if ims.get_meta('channels') > 1:
        image = FluorescentImage()
    else:
        image = Image()

    setup_image(image, ims, t, pos)

    Debug.set_context(t=t, pos=pos)

    image.keep_channel_image = True

    image.autorotate()
    image.find_channels()
    image.find_cells_in_channels()

    image.clean()

    return image


def processing_setup(args):
    global ims
    if ims is None:
        ims = MultiImageStack.open(args.input, treat_z_as_mp=args.zm)

    correct_windows_signal_handlers()

    try:
        import cv2
    except ImportError:
        pass


def main():
    global ims

    argparser = create_argparser()

    args = argparser.parse_args()

    def print_info(*inner_args):
        if not args.quiet:
            print(*inner_args)

    def print_warning(*inner_args):
        print(*inner_args, file=sys.stderr)

    if args.quiet:  # silence the progress bar filter
        progress_bar = silent_progress_bar
    else:
        progress_bar = fancy_progress_bar

    if not args.nb:
        print_info(banner())

    try:
        import matplotlib

        matplotlib.use('PDF')
    except ImportError:
        if args.debug:
            print_warning("matplotlib could not be imported. Debugging was disabled.")
            args.debug = False

    if args.debug:
        debug_init()
        if args.mp != 0:
            print_warning("Debugging enabled, concurrent processing disabled!")
            args.mp = 0

    if sys.maxsize <= 2 ** 32:
        print_warning("Warning, running on a 32 bit Python interpreter! This is most likely not what you want,"
                      "and it will significantly reduce functionality!")

    ims = MultiImageStack.open(args.input, treat_z_as_mp=args.zm)

    positions_to_process = args.multipoints

    if positions_to_process[-1] == float('Inf'):
        f = positions_to_process[-2]
        del positions_to_process[-2:-1]
        positions_to_process += range(f, ims.get_meta('multipoints'))

    positions_to_process = [p for p in positions_to_process if 0 <= p <= ims.get_meta('multipoints')]

    timepoints_to_process = args.timepoints
    if timepoints_to_process[-1] == float('Inf'):
        f = timepoints_to_process[-2]
        del timepoints_to_process[-2:-1]
        timepoints_to_process += range(f, ims.get_meta('timepoints'))

    timepoints_to_process = [t for t in timepoints_to_process if 0 <= t <= ims.get_meta('timepoints')]

    prettify_numpy_array = lambda arr, spaces: \
        repr(numpy.array(arr)).replace(')', '').replace('array(', ' ' * 6).replace(' ' * 6, ' ' * spaces)

    print_info("Beginning Processing:")
    #           123456789ABC :)
    print_info("Positions : " + prettify_numpy_array(positions_to_process, 0xC).lstrip())
    print_info("Timepoints: " + prettify_numpy_array(timepoints_to_process, 0xC).lstrip())

    results = {pos: {} for pos in positions_to_process}

    total = len(timepoints_to_process) * len(positions_to_process)
    processed = 0

    if args.mp < 0:
        args.mp = multiprocessing.cpu_count()

    print_info("Performing image analysis ...")

    to_process = list(itertools.product(timepoints_to_process, positions_to_process))

    if args.mp == 0:
        processing_setup(args)

        for t, pos in progress_bar(to_process):
            results[pos][t] = processing_frame(t, pos)
    else:
        print_info("... parallel on %(cores)d cores" % {'cores': args.mp})

        pool = multiprocessing.Pool(args.mp, processing_setup, [args])

        workerstates = []

        for t, pos in to_process:
            workerstates.append((t, pos, pool.apply_async(processing_frame, (t, pos))))

        progressbar_states = progress_bar(range(total))

        while len(workerstates) > 0:
            for i, (t, pos, state) in reversed(list(enumerate(workerstates))):
                if state.ready():
                    results[pos][t] = state.get()
                    del workerstates[i]
                    next(progressbar_states)

        pool.close()

    ####################################################################################################################

    tracked_results = {}

    print_info()

    print_info("Set-up for tracking ...")

    pi = progress_bar(range(sum([len(l) - 1 if len(l) > 0 else 0 for l in results.values()]) - 1))

    for pos, times in results.items():
        tracked_position = TrackedPosition()
        tracked_position.set_times(times)
        tracked_position.align_channels(progress_indicator=pi)
        tracked_position.remove_empty_channels()
        tracked_results[pos] = tracked_position

    print_info()

    print_info("Performing tracking ...")

    pi = progress_bar(range(sum([tp.get_tracking_work_size() for tp in tracked_results.values()]) - 1))

    for pos, times in results.items():
        tracked_position = tracked_results[pos]
        tracked_position.perform_tracking(progress_indicator=pi)
        tracked_position.remove_empty_channels_post_tracking()

    #( Output of textual results: )#####################################################################################

    def each_pos_k_tracking_tracker_channels_in_results(inner_tracked_results):
        for pos, tracking in inner_tracked_results.items():
            for inner_k in sorted(tracking.tracker_mapping.keys()):
                tracker = tracking.tracker_mapping[inner_k]
                channels = tracking.channel_accumulator[inner_k]
                yield pos, inner_k, tracking, tracker, channels


    if args.table_output is None:
        recipient = sys.stdout
    else:
        recipient = codecs.open(args.table_output, "wb+", "utf-8")

    print_info()
    print_info("Outputting tabular data ...")

    flat_results = list(each_pos_k_tracking_tracker_channels_in_results(tracked_results))

    try:
        table_dumper = QuickTableDumper(recipient=recipient)

        iterable = progress_bar(flat_results) if recipient is not sys.stdout else silent_progress_bar(flat_results)

        for pos, k, tracking, tracker, channels in iterable:
            analyze_tracking(tracker, table_dumper)

    finally:
        if recipient is not sys.stdout:
            recipient.close()

    #( Output of graphical tracking results: )##########################################################################

    if args.tracking_output is not None:

        try:
            import matplotlib
            import matplotlib.pylab
        except ImportError:
            print_warning("Tracking output enabled but matplotlib not found! Cannot proceed.")
            print_warning("Please install matplotlib ...")
            raise

        print_info("Outputting graphical tracking data ...")

        figdir = os.path.abspath(args.tracking_output)

        if not os.path.isdir(figdir):
            os.mkdir(figdir)

        for pos, k, tracking, tracker, channels in progress_bar(flat_results):
            plot_timeline(matplotlib.pylab, channels, tracker_to_cell_list(tracker),
                          figure_presetup=
                          lambda p: p.title("Channel #%02d (average cells = %.2f)" % (k, tracker.average_cells)),
                          figure_finished=
                          lambda p: p.savefig("%(dir)s/tracking_pt_%(mp)02d_chan_%(k)02d.pdf" %
                                              {'dir': figdir, 'mp': pos, 'k': k}),
                          show_images=True, show_overlay=True)

    #( Post-Tracking: Just write some tunables, if desired )############################################################

    if args.write_tunables:
        print_info()
        if os.path.isfile(args.write_tunables):
            print_warning("Tunable output will not overwrite existing files!")
            print_warning("NOT outputint tunables.")
        else:
            fname = os.path.abspath(args.write_tunables)
            print_info("Writing tunables to \"%(fname)s\"" % {'fname': fname})
            with codecs.open(fname, "wb+", "utf-8") as fp:
                json.dump(TunableManager.get_defaults(), fp, indent=4, sort_keys=True)

