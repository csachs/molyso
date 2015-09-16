# -*- coding: utf-8 -*-
"""
documentation
"""
from __future__ import division, unicode_literals, print_function

import numpy

from ..generic.otsu import threshold_otsu
from ..generic.signal import hamming_smooth,  simple_baseline_correction, find_extrema_and_prominence, \
    vertical_mean, threshold_outliers

from .. import DebugPlot, tunable


class Cell(object):
    __slots__ = ['local_top', 'local_bottom', 'channel']

    def __init__(self, top, bottom, channel):
        self.local_top = float(top)
        self.local_bottom = float(bottom)

        self.channel = channel

    @property
    def top(self):
        return self.channel.top + self.local_top

    @property
    def bottom(self):
        return self.channel.top + self.local_bottom

    @property
    def length(self):
        return abs(self.top - self.bottom)

    @property
    def centroid_1d(self):
        return (self.top + self.bottom) / 2.0

    @property
    def centroid(self):
        return [self.channel.centroid[0], self.centroid_1d]

    @property
    def cell_image(self):
        return self.crop_out_of_channel_image(self.channel.channel_image)

    def crop_out_of_channel_image(self, channel_image):
        return channel_image[self.local_top:self.local_bottom, :]

    def __lt__(self, other_cell):
        return self.local_top < other_cell.local_top


class Cells(object):
    """
        docstring
    """

    __slots__ = ['cells_list', 'channel', 'nearest_tree']

    cell_type = Cell

    def __init__(self, channel, bootstrap=True):

        self.cells_list = []

        self.channel = channel

        self.nearest_tree = None

        if not bootstrap:
            return

        for b, e in find_cells_in_channel(self.channel.channel_image):
            # ... this is the actual minimal size filtering
            if self.channel.image.mu_to_pixel(tunable('cells.minimal_length.in_mu', 1.0)) < e - b:
                self.cells_list.append(self.__class__.cell_type(b, e, self.channel))

    def __len__(self):
        return len(self.cells_list)

    def __iter__(self):
        return iter(self.cells_list)

    def clean(self):
        pass

    @property
    def centroids(self):
        return [cell.centroid for cell in self.cells_list]


def find_cells_in_channel(image):
    # processing is as always mainly performed on the intensity profile
    profile = vertical_mean(image)

    # empty channel detection
    thresholded_profile = threshold_outliers(profile, tunable('cells.empty_channel.skipping.outlier_times_sigma', 2.0))

    # if active, a non-empty channel must have a certain dynamic range min/max
    if ((thresholded_profile.max() - thresholded_profile.min()) / thresholded_profile.max()) < \
            tunable('cells.empty_channel.skipping.intensity_range_quotient', 0.5) and \
            tunable('cells.empty_channel.skipping', False):  # is off by default!
        return []

    # for cell detection, another intensity profile based on an Otsu binarization is used as well
    binary_image = image > threshold_otsu(image) * tunable('cells.otsu_bias', 1.0)
    profile_of_binary_image = vertical_mean(binary_image.astype(float))

    # the profile is first baseline corrected and smoothed ...
    profile = simple_baseline_correction(profile)
    profile = hamming_smooth(profile, tunable('cells.smoothing.length', 10))

    # the the smoothing steps above seem to subtly change the profile
    # in a python2 vs. python3 different way
    # thus we round them to get a reproducible workflow
    profile = profile.round(8)

    # ... then local extrema are searched
    extrema = find_extrema_and_prominence(profile, order=tunable('cells.extrema.order', 15))

    # based on the following filter function,
    # it will be decided whether a pair of extrema marks a cell or not
    # #1# size must be larger than zero
    # #2# the cell must have a certain 'blackness' (based on the Otsu binarization)
    # #3# the cell must have a certain prominence (difference from background brightness)

    # please note, while #1# looks like the minimum size criterion as described in the paper,
    # it is just a pre-filter, the actual minimal size filtering is done in the Cells class!
    # that way, the cell detection routine here is independent of more mundane aspects like calibration,
    # and changes in cell detection routine will still profit from the size-postprocessing

    def is_a_cell(last_pos, pos):
        return \
            pos - last_pos > 2 and \
            profile_of_binary_image[last_pos:pos].mean() < tunable('cells.filtering.maximum_brightness', 0.5) and \
            extrema.prominence[last_pos:pos].mean() > tunable('cells.filtering.minimum_prominence', 10.0)

    # possible positions are constructed, and a cell list is generated by checking them with the is_a_cell function
    positions = [_pos for _pos in extrema.maxima if extrema.prominence[_pos] > 0] + [profile.size]
    cells = [
        [_last_pos + 1, _pos - 1] for _last_pos, _pos in zip([0] + positions, positions)
        if is_a_cell(_last_pos, _pos)
        ]

    with DebugPlot('cell_detection', 'channel', 'graph') as p:
        p.title("Cell detection")
        p.imshow(numpy.transpose(image), aspect='auto', extent=(0, image.shape[0], 10 * image.shape[1], 0))
        p.imshow(numpy.transpose(binary_image), aspect='auto', extent=(0, image.shape[0], 0, -10 * image.shape[1]))
        p.plot(profile)

        p.plot(thresholded_profile)

        cell_lines = [pos for pos in cells for pos in pos]

        p.vlines(cell_lines,
                 [image.shape[1] * -10] * len(cell_lines),
                 [image.shape[1] * 10] * len(cell_lines),
                 colors='yellow')

    return cells
