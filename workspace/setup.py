#!/usr/bin/env python3
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="ai-collaboration-platform",
    version="1.1.0",
    author="Open Entity",
    author_email="entity@ai-collaboration.local",
    description="AI-to-AI Communication Protocol and Infrastructure",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/open-entity/ai-collaboration-platform",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-asyncio>=0.21",
            "pytest-cov>=4.0",
            "flake8>=6.0",
            "bandit>=1.7",
        ],
    },
    entry_points={
        "console_scripts": [
            "ai-peer=services.peer_service_runner:main",
            "ai-wallet=services.wallet_cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "": ["*.json", "*.yaml", "*.md"],
    },
)