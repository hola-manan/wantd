"""CLI: python -m wantd <reel-url-or-video-file> [--max-tier N] [--keep DIR]"""

import argparse
import logging
import sys

from wantd import pipeline


def main() -> None:
    ap = argparse.ArgumentParser(prog="wantd", description="Extract structured data from a reel.")
    ap.add_argument("target", help="Instagram/YouTube URL or a local video file")
    ap.add_argument("--max-tier", type=int, default=3, choices=[0, 1, 2, 3],
                    help="stop after this tier (cost control while testing)")
    ap.add_argument("--keep", metavar="DIR", help="keep the video, audio and frames in DIR")
    ap.add_argument("-q", "--quiet", action="store_true", help="only print the JSON")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    try:
        result = pipeline.run(args.target, max_tier=args.max_tier, keep_dir=args.keep)
    except Exception as e:
        sys.exit(f"error: {e}")
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
