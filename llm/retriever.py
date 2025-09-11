import os
import email
from email import policy
from email.parser import BytesParser

def load_eml_texts_from_folder(folder_path):
    email_texts = []

    for filename in os.listdir(folder_path):
        if filename.endswith(".eml"):
            filepath = os.path.join(folder_path, filename)
            with open(filepath, 'rb') as f:
                msg = BytesParser(policy=policy.default).parse(f)
                # Försök få tag på textinnehåll från kroppen
                body = msg.get_body(preferencelist=('plain'))
                if body:
                    text = body.get_content()
                    email_texts.append(text)

    return email_texts


def load_email_memory():
    folder_path = "email_memory"
    return load_eml_texts_from_folder(folder_path)
