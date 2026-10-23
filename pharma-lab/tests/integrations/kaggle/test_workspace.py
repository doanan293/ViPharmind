from pathlib import Path

from pharma_lab.integrations.kaggle.workspace import managed_staging_directory


def test_managed_staging_directory_is_removed_on_exit(tmp_path):
    with managed_staging_directory(tmp_path, prefix="stage-") as staging:
        marker = Path(staging) / "marker"
        marker.write_text("ok", encoding="utf-8")
        assert marker.is_file()
    assert not staging.exists()


def test_unwind_on_sigterm_is_a_no_op_outside_the_main_thread():
    import threading

    from pharma_lab.integrations.kaggle.workspace import unwind_on_sigterm

    errors: list[BaseException] = []

    def worker() -> None:
        try:
            with unwind_on_sigterm():
                pass
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert errors == []
