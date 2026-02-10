from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    # Database settings
    DB_USERNAME: str
    DB_PASSWORD: str
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    
    
    #llm settings
    OPENAI_API_KEY: str
    MODEL_NAME: str = "gpt-5.2"
    TEMPERATURE: float = 0.0
    
    # Vector store settings
    embedding_model: str = "text-embedding-3-large"
    
    # Additional settings
    COLLECTION_NAME: str = "billing_knowledge"
    DATA_DIR: str = "./data"
    CHROMA_DIR: str = "./vectordb/chroma"
    
    # Data ingestion settings
    PRO_CODE_FILE: str = "proCodeList.csv"
    MODIFIER_FILE: str = "modifierList.csv"
    ENM_FILE: str = "enmCodeList.csv"
    


    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )
    

    
settings = Config() #type: ignore