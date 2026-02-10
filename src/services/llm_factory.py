import sys
from pathlib import Path
from langchain_openai import ChatOpenAI
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from config.config import settings
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()






OpenAI(api_key=settings.OPENAI_API_KEY) 

def get_openai_llm():
    """
    Factory pattern to return the configured OpenAI LLM.
    Changes based on .env configuration.
    """
    
    llm = ChatOpenAI(
        model=settings.MODEL_NAME,
        temperature=settings.TEMPERATURE,
        streaming=True,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0,
    ) 
    return llm