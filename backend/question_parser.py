import re

def extract_numbers(question_text):
    return re.findall(r"\d+\.?\d*", question_text)
