"""Type aliases for the image arrays passed between modules.

Attributes:
    BgrImage: Height by width by 3 array in OpenCV blue, green, red channel order.
    GrayImage: Height by width single-channel 8-bit array.
    FloatImage: Floating-point working image used by accumulating filters.
"""

import numpy as np
from numpy.typing import NDArray

type BgrImage = NDArray[np.uint8]
type GrayImage = NDArray[np.uint8]
type FloatImage = NDArray[np.float32]
