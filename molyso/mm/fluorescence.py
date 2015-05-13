# -*- coding: utf-8 -*-
"""

"""
from __future__ import division, unicode_literals, print_function

import numpy
from .image import Image
from .cell_detection import Cell, Cells
from .channel_detection import Channel, Channels
from ..generic.rotation import apply_rotate_and_cleanup
from ..generic.signal import fit_to_type


class FluorescentCell(Cell):
    __slots__ = ['fluorescences_mean', 'fluorescences_std']

    def __init__(self, *args, **kwargs):
        super(FluorescentCell, self).__init__(*args, **kwargs)

        fluor_count = len(self.channel.image.image_fluorescences)

        self.fluorescences_mean = [float('nan')] * fluor_count
        self.fluorescences_std = [float('nan')] * fluor_count

        try:  # reconstitution from flattened state will fail
              # due to missing image_fluorescence.
              # keep calm and carry on!

            for f in range(fluor_count):
                if self.channel.image.image_fluorescences[f] is None:
                    continue
                cell_img = self.channel.image.image_fluorescences[f][
                           (self.local_top + self.channel.real_top):(self.local_bottom + self.channel.real_top),
                           self.channel.left:self.channel.right]


                self.fluorescences_mean[f] = float(cell_img.mean())
                self.fluorescences_std[f] = float(numpy.std(cell_img))

        except (AttributeError, TypeError):
            pass

    @property
    def fluorescences(self):
        return [self.fluorescences_mean[f] - self.channel.image.background_fluorescences[f] for f in range(len(self.channel.image.image_fluorescences))]

    @property
    def fluorescences_raw(self):
        return self.fluorescences_mean


class FluorescentCells(Cells):
    cell_type = FluorescentCell


class FluorescentChannel(Channel):
    __slots__ = 'fluorescences_channel_image'
    cells_type = FluorescentCells

    def __init__(self, image, left, right, top, bottom):
        super(FluorescentChannel, self).__init__(image, left, right, top, bottom)

        fluor_count = len(image.image_fluorescences)

        self.fluorescences_channel_image = [None] * fluor_count

        for f in range(fluor_count):
            if image.image_fluorescences[f] is None:
                continue

            self.fluorescences_channel_image[f] = self.crop_out_of_image(image.image_fluorescences[f])



class FluorescentChannels(Channels):
    channel_type = FluorescentChannel


class FluorescentImage(Image):
    channels_type = FluorescentChannels

    def __init__(self):
        super(FluorescentImage, self).__init__()

        self.keep_fluorescences_image = False
        self.pack_fluorescences_image = False

        self.image_fluorescences = []
        self.original_image_fluorescences = []
        self.background_fluorescences = []

        self.channels_cells_fluorescences_mean = None
        self.channels_cells_fluorescences_std = None

        self.channel_fluorescences_images = None

    def setup_add_fluorescence(self, fimg):
        self.image_fluorescences.append(fimg)
        self.original_image_fluorescences.append(fimg)

        self.background_fluorescences.append(0.0)

    def autorotate(self):
        super(FluorescentImage, self).autorotate()
        self.image_fluorescences = [
            apply_rotate_and_cleanup(fluorescence_image, self.angle)[0]
            for fluorescence_image in self.image_fluorescences]

    def clean(self):
        super(FluorescentImage, self).clean()
        fluor_count = len(self.image_fluorescences)
        self.image_fluorescences = [None] * fluor_count
        self.original_image_fluorescences = [None] * fluor_count

    def find_channels(self):
        super(FluorescentImage, self).find_channels()

        fluor_count = len(self.image_fluorescences)

        if len(self.channels) == 0:
            # do something more meaningful ?!
            self.background_fluorescences = [0.0] * fluor_count
        else:

            for i in range(fluor_count):

                fluorescence_image = self.image_fluorescences[i]

                background_fluorescence_means = numpy.zeros((len(self.channels) - 1, 2), dtype=numpy.float64)

                channel_iterator = iter(self.channels)

                previous_channel = next(channel_iterator)
                for n, next_channel in enumerate(channel_iterator):
                    background_fragment = fluorescence_image[next_channel.real_top:next_channel.real_bottom,
                                          previous_channel.right:next_channel.left]
                    background_fluorescence_means[n, 0] = background_fragment.mean()
                    background_fluorescence_means[n, 1] = background_fragment.size
                    previous_channel = next_channel

                background_fluorescence_means[:, 0] *= background_fluorescence_means[:, 1]

                self.background_fluorescences[i] = numpy.sum(background_fluorescence_means[:, 0]) / \
                                                   numpy.sum(background_fluorescence_means[:, 1])

    def flatten(self):
        channels = self.channels

        fluor_count = len(self.image_fluorescences)

        self.channels_cells_fluorescences_mean = [[[cc.fluorescences_mean[f] for cc in c.cells] for c in channels] for f in range(fluor_count)]
        self.channels_cells_fluorescences_std = [[[cc.fluorescences_std[f] for cc in c.cells] for c in channels] for f in range(fluor_count)]

        if self.keep_fluorescences_image:
            def _pack_image(image):
                if self.pack_fluorescences_image is False:
                    return image
                else:
                    if image is None:
                        return image
                    else:
                        return fit_to_type(image, self.pack_fluorescences_image)

            self.channel_fluorescences_images = [[_pack_image(ci) for ci in c.fluorescences_channel_image] for c in channels]


        super(FluorescentImage, self).flatten()


    def unflatten(self):
        super(FluorescentImage, self).unflatten()
        fluor_count = len(self.image_fluorescences)
        for n, channel in enumerate(self.channels):
            if self.channel_fluorescences_images is not None:
                channel.fluorescences_channel_image = self.channel_fluorescences_images[n]

            for cn, cell in enumerate(channel.cells):
                cell.fluorescences_mean = [self.channels_cells_fluorescences_mean[f][n][cn] for f in range(fluor_count)]
                cell.fluorescences_std = [self.channels_cells_fluorescences_std[f][n][cn] for f in range(fluor_count)]
        self.channels_cells_fluorescences_mean = None
        self.channels_cells_fluorescences_std = None
        self.channel_fluorescences_images = None
