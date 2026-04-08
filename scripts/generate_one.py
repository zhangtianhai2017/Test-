"""CLI script: generate a single bikini model."""

import argparse
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    parser = argparse.ArgumentParser(description="Generate a 3D bikini model")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--ai", action="store_true", help="Use AI design suggestions")
    parser.add_argument("--no-physics", action="store_true", help="Skip physics validation")
    parser.add_argument("--output", type=str, default="output", help="Output directory")
    parser.add_argument("--tex-res", type=int, default=1024, help="Texture resolution")
    args = parser.parse_args()

    from bikini_generator.pipeline import generate_bikini

    print(f"Generating bikini (seed={args.seed}, ai={args.ai}, physics={not args.no_physics})...")
    result = generate_bikini(
        seed=args.seed,
        use_ai=args.ai,
        skip_physics=args.no_physics,
        output_dir=args.output,
        texture_resolution=args.tex_res,
    )

    if result.success:
        print(f"\nSuccess! Model ID: {result.model_id}")
        print(f"Design: {result.design.to_text()}")
        print(f"Time: {result.generation_time:.2f}s (retries: {result.retries})")
        print(f"\nFiles:")
        for key, path in result.files.items():
            print(f"  {key}: {path}")
    else:
        print(f"\nFailed: {result.message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
