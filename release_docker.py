#!/usr/bin/env python3

import argparse
import logging
import re
import subprocess
import sys
from pathlib import Path

# CONFIGURATION
PLATFORM = "linux/amd64"
BUILDER_NAME = "buildx_builder"
REGISTRY = "docker.io"
IMAGE = f"{REGISTRY}/tubsmaster/solaredge2mqtt"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)


def run(*cmd):
    logging.info("$ %s", " ".join(cmd))
    try:
        return subprocess.run(
            cmd, check=True, capture_output=True, text=True
        ).stdout.strip()
    except subprocess.CalledProcessError as error:
        logging.error("Command failed with exit code %s", error.returncode)
        if error.stdout:
            logging.error("stdout:\n%s", error.stdout.strip())
        if error.stderr:
            logging.error("stderr:\n%s", error.stderr.strip())
        raise

def ensure_docker_login():
    """Ensures Docker is logged into the registry."""
    logging.info("Checking registry authentication for: %s", REGISTRY)
    run("docker", "login", REGISTRY)

def ensure_buildx_builder():
    """Ensures the BuildKit builder container exists, is started, and is selected."""
    logging.info("Checking BuildX builder: %s", BUILDER_NAME)

    # Check if builder instance already exists in buildx
    res = subprocess.run(
        ["docker", "buildx", "inspect", BUILDER_NAME],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    if res.returncode == 0:
        logging.info("Builder '%s' exists. Starting/bootstrapping...", BUILDER_NAME)
        run("docker", "buildx", "use", BUILDER_NAME)
        run("docker", "buildx", "inspect", "--bootstrap")
    else:
        logging.info("Builder '%s' does not exist. Creating and starting...", BUILDER_NAME)
        run(
            "docker", "buildx", "create",
            "--name", BUILDER_NAME,
            "--use",
            "--driver", "docker-container",
            "--driver-opt", "network=host",
            "--bootstrap"
        )

def is_valid_semver(v: str) -> bool:
    return bool(re.match(r"^\d+\.\d+\.\d+$", v))


def parse_version(v: str) -> tuple:
    return tuple(map(int, v.split('.')))


def main():
    parser = argparse.ArgumentParser(description="Release script for tubshub")
    parser.add_argument(
        "--keep-version",
        action="store_true",
        help="Skip prompting and release using the current VERSION file as-is",
    )
    args = parser.parse_args()

    # Ensure the working tree is clean.
    if run("git", "status", "--porcelain", "--untracked-files=no"):
        logging.error("Error: Working tree is not clean; commit or stash changes first")
        sys.exit(1)

    branch = run("git", "branch", "--show-current")
    if not branch:
        logging.error("Error: Detached HEAD")
        sys.exit(1)

    run("git", "fetch", "origin", branch)
    if run("git", "log", f"origin/{branch}..HEAD", "--oneline"):
        logging.error(f"Error: Local commits need pushing on {branch}")
        sys.exit(1)

    # Read current version
    version_path = Path("VERSION")
    current_version = version_path.read_text().strip()
    logging.info("Current version: %s", current_version)

    if args.keep_version:
        logging.info("Skipping version prompt (--keep-version specified)")
        version = current_version
    else:
        # Prompt user for new version
        try:
            new_version = input(f"Enter new version (current is {current_version}): ").strip()
        except (KeyboardInterrupt, EOFError):
            logging.warning("\nInterrupted by user")
            sys.exit(130)

        if not new_version:
            logging.error("Error: No version provided")
            sys.exit(1)

        # Validate version format (X.Y.Z)
        if not is_valid_semver(new_version):
            logging.error("Error: Version '%s' is invalid. Must follow the X.Y.Z format (e.g., 1.2.3)", new_version)
            sys.exit(1)

        # Check if new version is higher than current version
        if parse_version(new_version) <= parse_version(current_version):
            logging.error("Error: New version (%s) must be higher than current version (%s)", new_version, current_version)
            sys.exit(1)

        # Write new version to file and commit/push changes
        version_path.write_text(f"{new_version}\n")
        logging.info("Updated VERSION file to %s", new_version)

        try:
            logging.info("Committing and pushing version bump")
            run("git", "add", "VERSION")
            run("git", "commit", "-m", f"Bump version to {new_version}")
            run("git", "push", "origin", branch)
        except subprocess.CalledProcessError as error:
            logging.error("Failed to commit and push version bump: %s", error)
            sys.exit(1)

        version = new_version

    tag = f"v{version}"
    logging.info("Releasing version %s", version)

    run("git", "fetch", "--tags", "origin")

    if run("git", "ls-remote", "--tags", "--refs", "origin", f"refs/tags/{tag}"):
        logging.error("Tag %s already exists; skipping release", tag)
        return

    if run("git", "tag", "--list", tag):
        logging.error(f"Tag {tag} already exists locally")

    try:
        logging.info("Creating and pushing Git tag %s", tag)
        run("git", "tag", tag)
        run("git", "push", "origin", tag)

        ensure_docker_login()
        ensure_buildx_builder()

        logging.info("Building and pushing %s:%s", IMAGE, version)
        run(
            "docker", "buildx", "build",
            "--platform", PLATFORM,
            "--tag", f"{IMAGE}:{version}",
            "--tag", f"{IMAGE}:latest",
            "--push", ".",
        )
        logging.info("Release successful: %s:%s", IMAGE, version)
    except (subprocess.CalledProcessError, OSError, KeyboardInterrupt) as error:
        if isinstance(error, KeyboardInterrupt):
            logging.warning("Interrupted by user")
        else:
            logging.error("Release failed: %s", error)

        logging.info("Cleaning up Git tags")
        subprocess.run(["git", "push", "--delete", "origin", tag])
        subprocess.run(["git", "tag", "--delete", tag])
        sys.exit(130 if isinstance(error, KeyboardInterrupt) else 1)


if __name__ == "__main__":
    main()
