from forlabs_mcp.client.partial import PartialResult, combine


def test_is_partial_reflects_warnings() -> None:
    result = PartialResult(data=[1, 2, 3], warnings=["row 4 was malformed"])
    assert result.is_partial is True


def test_ok_has_no_warnings_and_is_not_partial() -> None:
    result = PartialResult.ok([1, 2, 3])
    assert result.warnings == []
    assert result.is_partial is False


def test_combine_merges_data_and_warnings_from_multiple_results() -> None:
    first = PartialResult(data=[1, 2], warnings=["study A failed"])
    second = PartialResult.ok([3, 4])
    third = PartialResult(data=[5], warnings=["study C failed"])

    combined = combine([first, second, third])

    assert combined.data == [1, 2, 3, 4, 5]
    assert combined.warnings == ["study A failed", "study C failed"]
    assert combined.is_partial is True


def test_combine_of_all_successful_results_is_not_partial() -> None:
    combined = combine([PartialResult.ok([1]), PartialResult.ok([2])])
    assert combined.data == [1, 2]
    assert combined.is_partial is False


def test_combine_of_empty_list_yields_empty_result() -> None:
    combined = combine([])
    assert combined.data == []
    assert combined.warnings == []
