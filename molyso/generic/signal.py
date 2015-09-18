# -*- coding: utf-8 -*-
"""
signal processing helper routines
"""

from __future__ import division, unicode_literals, print_function
from collections import namedtuple
import warnings

import scipy.signal
import scipy.interpolate

from .smoothing import hamming_smooth
from .fft import *


def find_phase(signal_1=None, signal_2=None,
               fft_1=None, fft_2=None,
               return_1=False, return_2=False):
    """
    Finds the phase (time shift) between two signals.
    Either signalX or fftX should be set; the FFTs can be returned
    in order to cache them locally...

    :param signal_1: first input signal
    :type signal_1: numpy.ndarray or None
    :param signal_2: second input signal
    :type signal_2: numpy.ndarray or None
    :param fft_1: first input fft
    :type fft_1: numpy.ndarray or None
    :param fft_2: second input fft
    :type fft_2: numpy.ndarray or None
    :param return_1: whether fft1 should be returned
    :type return_1: bool
    :param return_2: whether fft2 should be returned
    :type return_2: bool
    :return: (shift, (fft1 if return_1), (fft2 if return_2))
    :rtype: tuple

    >>> find_phase(numpy.array([0, 1, 0, 0, 0]), numpy.array([0, 0, 0, 1, 0]))
    (2,)
    """

    if signal_1 is not None and fft_1 is None:
        fft_1 = fft(signal_1)
    if signal_2 is not None and fft_2 is None:
        fft_2 = fft(signal_2)

    corr = ifft(fft_1 * -fft_2.conjugate())

    corr = numpy.absolute(corr)
    the_max = numpy.argmax(corr)
    # if the_max > 2 and the_max < (len(corr) - 2):
    #    sur = corr[the_max-1:the_max+2]
    #    the_max += -0.5*sur[0] + 0.5*sur[2]

    the_max = -the_max if the_max < len(fft_1) / 2 else len(fft_1) - the_max

    result = (the_max,)
    if return_1:
        result += (fft_1,)
    if return_2:
        result += (fft_2,)
    return result


class ExtremeAndProminence(namedtuple('ExtremeAndProminence', ['maxima', 'minima', 'signal', 'order', 'max_spline',
                                                               'min_spline', 'xpts', 'max_spline_points',
                                                               'min_spline_points', 'prominence'])):
    """
    Result of `find_extrema_and_prominence` call.

    :var maxima:
    :var minima:
    :var signal:
    :var order:
    :var max_spline:
    :var min_spline:
    :var xpts:
    :var max_spline_points:
    :var min_spline_points:
    :var prominence:
    """


def find_extrema_and_prominence(signal, order=5):
    """
    Generates various extra information / signals.

    :param signal: input signal
    :type signal: numpy.ndarray
    :param order: relative minima/maxima order, see other functions
    :type order: int
    :return: an ExtremeAndProminence object with various information members
    :rtype: ExtremeAndProminence

    >>> result = find_extrema_and_prominence(numpy.array([1, 2, 3, 2, 1, 0, 1, 2, 15, 2, -15, 2, 1]), 2)
    >>> result = result._replace(max_spline=None, min_spline=None)  # just for doctests
    >>> result
    ExtremeAndProminence(maxima=array([2, 8]), minima=array([ 5, 10]), signal=array([  1,   2,   3,   2,   1,   0,   1,   2,  15,   2, -15,   2,   1]), order=2, max_spline=None, min_spline=None, xpts=array([  0.,   1.,   2.,   3.,   4.,   5.,   6.,   7.,   8.,   9.,  10.,
            11.,  12.]), max_spline_points=array([  3.    ,   2.4875,   3.    ,   4.3125,   6.2   ,   8.4375,
            10.8   ,  13.0625,  15.    ,  16.3875,  17.    ,  16.6125,  15.    ]), min_spline_points=array([ -9.73055091e-16,   3.38571429e+00,   4.71428571e+00,
             4.35000000e+00,   2.65714286e+00,   5.21804822e-15,
            -3.25714286e+00,  -6.75000000e+00,  -1.01142857e+01,
            -1.29857143e+01,  -1.50000000e+01,  -1.57928571e+01,
            -1.50000000e+01]), prominence=array([  3.        ,  -0.89821429,  -1.71428571,  -0.0375    ,
             3.54285714,   8.4375    ,  14.05714286,  19.8125    ,
            25.11428571,  29.37321429,  32.        ,  32.40535714,  30.        ]))
    """
    # we are FORCING some kind of result here, although it might be meaningless

    maxima = numpy.array([numpy.argmax(signal)])
    iorder = order
    while iorder > 0:
        try:
            maxima = relative_maxima(signal, order=iorder)
        except ValueError:
            iorder -= 1
            continue
        break

    if len(maxima) == 0:
        maxima = numpy.array([numpy.argmax(signal)])

    minima = numpy.array([numpy.argmin(signal)])
    iorder = order
    while iorder > 0:
        try:
            minima = relative_minima(signal, order=iorder)
        except ValueError:
            iorder -= 1
            continue
        break
    if len(minima) == 0:
        minima = numpy.array([numpy.argmin(signal)])

    maximaintpx = numpy.zeros(len(maxima) + 2)
    maximaintpy = numpy.copy(maximaintpx)

    minimaintpx = numpy.zeros(len(minima) + 2)
    minimaintpy = numpy.copy(minimaintpx)

    maximaintpx[0] = 0
    maximaintpx[1:-1] = maxima[:]
    maximaintpx[-1] = len(signal) - 1

    maximaintpy[0] = signal[maxima][0]
    maximaintpy[1:-1] = signal[maxima][:]
    maximaintpy[-1] = signal[maxima][-1]

    minimaintpx[0] = 0
    minimaintpx[1:-1] = minima[:]
    minimaintpx[-1] = len(signal) - 1

    minimaintpy[0] = signal[minima][0]
    minimaintpy[1:-1] = signal[minima][:]
    minimaintpy[-1] = signal[minima][-1]

    k = 3
    if len(maximaintpy) <= 3:
        k = len(maximaintpy) - 1
    if k < 1:
        def max_spline(arg):
            """

            :param arg:
            :return:
            """
            arg = numpy.zeros_like(arg)
            arg[:] = float('Inf')
            return arg
    else:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            max_spline = scipy.interpolate.UnivariateSpline(maximaintpx, maximaintpy, bbox=[0, len(signal)], k=k)

    k = 3
    if len(minimaintpy) <= 3:
        k = len(minimaintpy) - 1
    if k < 1:
        def min_spline(arg):
            """

            :param arg:
            :return:
            """
            arg = numpy.zeros_like(arg)
            arg[:] = float('-Inf')
            return arg
    else:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            min_spline = scipy.interpolate.UnivariateSpline(minimaintpx, minimaintpy, bbox=[0, len(signal)], k=k)

    xpts = numpy.linspace(0, len(signal) - 1, len(signal))

    maxsy = max_spline(xpts)
    minsy = min_spline(xpts)

    return ExtremeAndProminence(maxima, minima, signal, order, max_spline, min_spline, xpts, maxsy, minsy,
                                maxsy - minsy)


def simple_baseline_correction(signal, window_width=None):
    """
    Performs a simple baseline correction by subtracting a strongly smoothed version of the signal from itself.

    :param signal: input signal
    :param window_width: smoothing window width
    :return:

    >>> simple_baseline_correction(numpy.array([10, 11, 12, 11, 10]))
    array([-1.        ,  0.375     ,  1.        , -0.375     , -0.96428571])
    """
    if window_width is None or window_width > len(signal):
        window_width = len(signal)

    return signal - hamming_smooth(signal, window_width, no_cache=True)


def vertical_mean(image):
    """
    Calculates the vertical mean of an image.
    Note: Image is assumed HORIZONTAL x VERTICAL.

    :param image:
    :return:

    >>> vertical_mean(numpy.array([[ 1,  2,  3,  4],
    ...                            [ 5,  6,  7,  8],
    ...                            [ 9, 10, 11, 12],
    ...                            [13, 14, 15, 16]]))
    array([  2.5,   6.5,  10.5,  14.5])
    """
    return numpy.average(image, axis=1)


def horizontal_mean(image):
    """
    Calculates the horizontal mean of an image.
    Note: Image is assumed HORIZONTAL x VERTICAL.

    :param image: input image
    :type image: numpy.ndarray
    :return:

    >>> horizontal_mean(numpy.array([[ 1,  2,  3,  4],
    ...                            [ 5,  6,  7,  8],
    ...                            [ 9, 10, 11, 12],
    ...                            [13, 14, 15, 16]]))
    array([  7.,   8.,   9.,  10.])
    """
    return numpy.average(image, axis=0)


def relative_maxima(signal, order=1):
    """

    :param signal:
    :param order:
    :return:

    >>> relative_maxima(numpy.array([1, 2, 3, 2, 1, 0, 1, 2, 15, 2, -15, 2, 1]), 2)
    array([2, 8])
    """
    value, = scipy.signal.argrelmax(signal, order=order)
    return value


def relative_minima(signal, order=1):
    """

    :param signal:
    :param order:
    :return:

    >>> relative_minima(numpy.array([1, 2, 3, 2, 1, 0, 1, 2, 15, 2, -15, 2, 1]), 2)
    array([ 5, 10])
    """
    value, = scipy.signal.argrelmin(signal, order=order)
    return value


def normalize(data):
    """
    normalizes the values in arr to 0 - 1

    :param data: input array
    :return: normalized array

    >>> normalize(numpy.array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]))
    array([ 0. ,  0.1,  0.2,  0.3,  0.4,  0.5,  0.6,  0.7,  0.8,  0.9,  1. ])

    >>> normalize(numpy.array([10, 15, 20]))
    array([ 0. ,  0.5,  1. ])
    """
    result = data.astype(float)
    result -= result.min()
    result /= result.max()
    return result


# noinspection PyUnresolvedReferences
def fit_to_type(image, new_dtype):
    """

    :param image:
    :param new_dtype:
    :return:

    >>> fit_to_type(numpy.array([-7, 4, 18, 432]), numpy.uint8)
    array([  0,   6,  14, 255], dtype=uint8)
    >>> fit_to_type(numpy.array([-7, 4, 18, 432]), numpy.int8)
    array([-128, -121, -113,  127], dtype=int8)
    >>> fit_to_type(numpy.array([-7, 4, 18, 432]), numpy.bool)
    array([False, False, False,  True], dtype=bool)
    >>> fit_to_type(numpy.array([-7, 4, 18, 432]), numpy.float32)
    array([  -7.,    4.,   18.,  432.], dtype=float32)
    """
    scaled_img = normalize(image)
    to_type = numpy.dtype(new_dtype)
    if to_type.kind == 'f':
        return image.astype(to_type)
    elif to_type.kind == 'u':
        return (scaled_img * (2 ** (to_type.itemsize * 8) - 1)).astype(to_type)
    elif to_type.kind == 'i':
        return (scaled_img * (2 ** (to_type.itemsize * 8) - 1) - (2 ** (to_type.itemsize * 8 - 1))).astype(to_type)
    elif to_type.kind == 'b':
        return scaled_img > 0.5
    else:
        raise TypeError("Unsupported new_dtype value used for rescale_and_fit_to_type used!")


# TODO: Improve this function!
def threshold_outliers(data, times_std=2.0):
    """
    removes outliers


    :param data:
    :param times_std:
    :return:

    >>> threshold_outliers(numpy.array([10, 9, 11, 40, 8, 12, 14, 7]), times_std=1.0)
    array([10,  9, 11, 20,  8, 12, 14,  7])
    """

    data = data.copy()
    median = numpy.median(data)
    std = numpy.std(data)
    data[(data - median) > (times_std * std)] = median + (times_std * std)
    data[((data - median) < 0) & (abs(data - median) > times_std * std)] = median - (times_std * std)
    return data


def outliers(data, times_std=2.0):
    """

    :param data:
    :param times_std:
    :return:

    >>> outliers(numpy.array([10, 9, 11, 40, 8, 12, 14, 7]), times_std=1.0)
    array([False, False, False,  True, False, False, False, False], dtype=bool)
    """

    return numpy.absolute(data - numpy.median(data)) > (times_std * numpy.std(data))


def remove_outliers(data, times_std=2.0):
    """

    :param data:
    :param times_std:
    :return:

    >>> remove_outliers(numpy.array([10, 9, 11, 40, 8, 12, 14, 7]), times_std=1.0)
    array([10,  9, 11,  8, 12, 14,  7])
    """

    try:
        return data[~outliers(data, times_std)]
    except TypeError:
        return data


def find_insides(signal):
    """

    :param signal:
    :return:

    >>> find_insides(numpy.array([False, False, True, True, True, False, False, True, True, False, False]))
    array([[2, 5],
           [7, 9]])
    """
    # had a nicer numpy using solution ... which failed in some cases ...
    # plain, but works.
    pairs = []
    last_true = None
    for n, i in enumerate(signal):
        if i and not last_true:
            last_true = n
        elif not i and last_true:
            pairs.append([last_true, n])
            last_true = None

    if last_true:
        pairs.append([last_true, len(signal)-1])

    return numpy.array(pairs)


def one_every_n(length, n=1, shift=0):
    """

    :param length:
    :param n:
    :param shift:
    :return:

    >>> one_every_n(10, n=2, shift=0)
    array([ 1.,  0.,  1.,  0.,  1.,  0.,  1.,  0.,  1.,  0.])
    >>> one_every_n(10, n=2, shift=1)
    array([ 0.,  1.,  0.,  1.,  0.,  1.,  0.,  1.,  0.,  1.])
    """
    signal = numpy.zeros(int(length))
    indices = numpy.arange(shift % n, length, n, dtype=numpy.int32)
    indices = indices[indices < len(signal)]
    signal[indices] = 1
    return signal


def each_image_slice(image, steps, direction='vertical'):
    """

    :param image:
    :param steps:
    :param direction:
    :return:

    >>> list(each_image_slice(numpy.ones((4, 4,)), 2, direction='vertical'))
    [(0, 2, array([[ 1.,  1.],
           [ 1.,  1.],
           [ 1.,  1.],
           [ 1.,  1.]])), (1, 2, array([[ 1.,  1.],
           [ 1.,  1.],
           [ 1.,  1.],
           [ 1.,  1.]]))]
    >>> list(each_image_slice(numpy.ones((4, 4,)), 2, direction='horizontal'))
    [(0, 2, array([[ 1.,  1.,  1.,  1.],
           [ 1.,  1.,  1.,  1.]])), (1, 2, array([[ 1.,  1.,  1.,  1.],
           [ 1.,  1.,  1.,  1.]]))]
    """
    if direction == 'vertical':
        step = image.shape[1] // steps
        for n in range(steps):
            yield n, step, image[:, step * n:step * (n + 1)]
    elif direction == 'horizontal':
        step = image.shape[0] // steps
        for n in range(steps):
            yield n, step, image[step * n:step * (n + 1), :]
    else:
        raise ValueError("Unknown direction passed.")
