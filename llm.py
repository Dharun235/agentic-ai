from ollama import Client
from config import settings

MODEL = settings["chat_model"]
ollama = Client(host=settings["ollama_host"])


def answer(question, context):
    prompt = f"""Answer the question using only the context.
Give a short, direct answer.
Do not add information that was not asked for.
If the answer is not in the context, say "I don't know."

Context:
{context}

Question:
{question}
"""

    response = ollama.chat(model=MODEL, messages=[{"role": "user", "content": prompt}], options={"temperature": 0})

    return response.message.content
