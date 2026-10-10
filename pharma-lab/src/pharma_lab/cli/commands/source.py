from __future__ import annotations

import http.client
from datetime import date
from pathlib import Path
from typing import Annotated
from urllib.request import Request, urlopen

import typer

from pharma_lab.cli.runtime import (
    CommandResult,
    CommandStatus,
    run_handler,
    state_from_context,
)
from pharma_lab.config.paths import (
    LEAFLETS_DIR,
)
from pharma_lab.corpus.sources.crawl import (
    CrawlFetchError,
    CrawlRequest,
    crawl_leaflets,
)

source_app = typer.Typer(no_args_is_help=True, add_completion=False)


@source_app.command("crawl")
def crawl(
    ctx: typer.Context,
    leaflets_dir: Annotated[Path, typer.Option("--leaflets-dir")] = LEAFLETS_DIR,
    sitemap_url: Annotated[str | None, typer.Option("--sitemap-url")] = None,
    workers: Annotated[int, typer.Option("--workers")] = 8,
    request_timeout_seconds: Annotated[
        float, typer.Option("--request-timeout-seconds")
    ] = 10.0,
    force: Annotated[bool, typer.Option("--force")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    def run() -> CommandResult:
        result = crawl_leaflets(
            CrawlRequest(
                leaflets_dir,
                sitemap_url,
                workers,
                request_timeout_seconds,
                force,
                dry_run,
            ),
            _fetch,
            today=date.today(),
        )
        return CommandResult(
            "source crawl",
            CommandStatus.COMPLETE,
            result.manifest_path,
            {
                "total": result.total,
                "downloaded": result.downloaded,
                "skipped": result.skipped,
                "failed": result.failed,
            },
        )

    run_handler(state_from_context(ctx), run)


def _fetch(url: str, timeout: float) -> bytes:
    request = Request(url, headers={"User-Agent": "pharma-lab"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.read()
    except (OSError, http.client.HTTPException, ValueError) as exc:
        raise CrawlFetchError(f"{url}: {exc}") from exc
