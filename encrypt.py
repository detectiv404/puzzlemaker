from cryptography.fernet import Fernet


def generate_key() -> str:
    return Fernet.generate_key().decode()


def encrypt_text(text: str, key: str) -> str:
    return Fernet(key.encode()).encrypt(text.encode()).decode()


def decrypt_text(encrypted: str, key: str) -> str:
    return Fernet(key.encode()).decrypt(encrypted.encode()).decode()
