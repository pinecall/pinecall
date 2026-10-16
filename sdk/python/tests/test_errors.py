"""One root for every error the package raises."""

import pytest

from pinecall import PinecallError, WireError


def test_an_error_of_the_package_is_caught_by_its_root_and_says_its_sentence() -> None:
    with pytest.raises(PinecallError, match=r"^the sentence a person reads$"):
        raise PinecallError("the sentence a person reads")


def test_the_root_is_an_exception_and_not_a_base_exception_only() -> None:
    assert issubclass(PinecallError, Exception)


def test_a_frame_that_does_not_fit_is_an_error_of_the_package() -> None:
    assert issubclass(WireError, PinecallError)
