"""
Obfuscation utilities for secure API key storage.

This module provides simple but effective obfuscation for API keys to prevent
accidental leakage through Agent tools (read_file, terminal, prompt injection).

Note: This is obfuscation, not strong encryption. It's designed to protect against
unintentional exposure via Agent tools, not against determined attackers.
"""

import base64
import hashlib
import platform
import json
from pathlib import Path
from typing import Optional


class KeyObfuscator:
    """
    Obfuscate and deobfuscate API keys using device fingerprint.

    This prevents Agent tools from accidentally reading plaintext API keys.
    """

    # Storage path
    CREDENTIALS_FILE = Path("data/credentials.encrypted")

    # Obfuscation version (for future upgrades)
    VERSION = "v1"

    @staticmethod
    def _get_machine_id() -> bytes:
        """
        Generate a machine-specific identifier for obfuscation.

        Returns a 32-byte hash based on machine characteristics.
        """
        # Collect machine-specific data
        machine_data = f"{platform.node()}-{platform.machine()}-{platform.system()}"
        return hashlib.sha256(machine_data.encode()).digest()

    @classmethod
    def obfuscate(cls, api_key: str) -> str:
        """
        Obfuscate an API key using device fingerprint.

        Args:
            api_key: The plaintext API key

        Returns:
            Obfuscated string (version:data:checksum format)
        """
        machine_id = cls._get_machine_id()

        # XOR the API key with machine ID
        key_bytes = api_key.encode()
        obfuscated = bytes(
            b ^ machine_id[i % len(machine_id)]
            for i, b in enumerate(key_bytes)
        )

        # Encode to base64
        encoded = base64.b64encode(obfuscated).decode()

        # Calculate checksum
        checksum = hashlib.md5(encoded.encode()).hexdigest()[:8]

        # Return with version prefix
        return f"{cls.VERSION}:{encoded}:{checksum}"

    @classmethod
    def deobfuscate(cls, obfuscated: str) -> Optional[str]:
        """
        Deobfuscate an API key.

        Args:
            obfuscated: The obfuscated string

        Returns:
            Plaintext API key, or None if deobfuscation fails
        """
        try:
            # Parse format
            parts = obfuscated.split(":")
            if len(parts) != 3 or parts[0] != cls.VERSION:
                return None

            version, encoded, checksum = parts

            # Verify checksum
            expected_checksum = hashlib.md5(encoded.encode()).hexdigest()[:8]
            if checksum != expected_checksum:
                return None

            # Decode from base64
            obfuscated_bytes = base64.b64decode(encoded)

            # XOR back with machine ID
            machine_id = cls._get_machine_id()
            decrypted = bytes(
                b ^ machine_id[i % len(machine_id)]
                for i, b in enumerate(obfuscated_bytes)
            )

            return decrypted.decode()

        except Exception:
            return None

    @classmethod
    def save_credentials(cls, credentials: dict) -> None:
        """
        Save obfuscated credentials to file.

        Args:
            credentials: Dictionary with provider configuration
                        Example: {"qwen": {"api_key": "sk-xxx", "base_url": "...", "model": "..."}}
        """
        # Obfuscate each API key
        obfuscated_data = {}
        for provider, config in credentials.items():
            obfuscated_config = config.copy()
            if "api_key" in config:
                obfuscated_config["api_key"] = cls.obfuscate(config["api_key"])
            obfuscated_data[provider] = obfuscated_config

        # Ensure directory exists
        cls.CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)

        # Save to file
        with open(cls.CREDENTIALS_FILE, "w", encoding="utf-8") as f:
            json.dump(obfuscated_data, f, indent=2, ensure_ascii=False)

    @classmethod
    def load_credentials(cls) -> dict:
        """
        Load and deobfuscate credentials from file.

        Returns:
            Dictionary with deobfuscated credentials
        """
        if not cls.CREDENTIALS_FILE.exists():
            return {}

        try:
            with open(cls.CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                obfuscated_data = json.load(f)

            # Deobfuscate each API key
            credentials = {}
            for provider, config in obfuscated_data.items():
                deobfuscated_config = config.copy()
                if "api_key" in config:
                    decrypted = cls.deobfuscate(config["api_key"])
                    if decrypted is None:
                        # Deobfuscation failed (wrong machine or corrupted)
                        continue
                    deobfuscated_config["api_key"] = decrypted
                credentials[provider] = deobfuscated_config

            return credentials

        except Exception:
            return {}

    @classmethod
    def has_credentials(cls) -> bool:
        """Check if credentials file exists."""
        return cls.CREDENTIALS_FILE.exists()

    @classmethod
    def get_api_key(cls, provider: str) -> Optional[str]:
        """
        Get API key for a specific provider.

        Args:
            provider: Provider name (e.g., "qwen", "openai")

        Returns:
            API key or None if not found
        """
        credentials = cls.load_credentials()
        if provider in credentials:
            return credentials[provider].get("api_key")
        return None
