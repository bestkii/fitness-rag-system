from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "fitness_mock_3000.jsonl"
SPLIT_PATH = ROOT / "artifacts" / "dataset_split.json"
METRICS_PATH = ROOT / "artifacts" / "evaluation_metrics.json"
DB_PATH = ROOT / "fitness_vector_db_final"
RUNTIME_DIR = ROOT / "runtime"
DRAFTS_DIR = RUNTIME_DIR / "drafts"
XHS_PROFILE_DIR = RUNTIME_DIR / "xiaohongshu_chrome"
XHS_DB_PATH = RUNTIME_DIR / "xiaohongshu_topics.sqlite3"
PRIVATE_CORPUS_DIR = RUNTIME_DIR / "private_corpus"
PRIVATE_TEXTBOOK_DB_PATH = PRIVATE_CORPUS_DIR / "vector_db"
PRIVATE_TEXTBOOK_COLLECTION = "private_textbooks_v1"
PRIVATE_TEXTBOOK_METRICS_PATH = PRIVATE_CORPUS_DIR / "evaluation_metrics.json"
PRIVATE_REVIEW_DB_PATH = PRIVATE_CORPUS_DIR / "reviews.sqlite3"
PRIVATE_SOURCE_REGISTRY_PATH = PRIVATE_CORPUS_DIR / "source_registry.json"
PRIVATE_PAGE_PREVIEW_DIR = PRIVATE_CORPUS_DIR / "page_previews"
PRIVATE_APPROVED_DB_PATH = PRIVATE_CORPUS_DIR / "approved_vector_db"
PRIVATE_APPROVED_COLLECTION = "approved_private_textbooks_v1"

APP_NAME = "Fitness Evidence Studio"
COLLECTION_NAME = "fitness_evidence_2700"
EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
EMBEDDING_DIMENSION = 512
TOP_K = 3
RANDOM_SEED = 20260627
TEST_SIZE = 300
SPLIT_VERSION = 2
INDEXED_RECORDS = 2700

EXPERT_LABELS = {
    "exercise_physiology": "Exercise Physiology",
    "clinical_nutrition": "Clinical Nutrition",
    "media_discourse": "Media Discourse",
    "sports_biomechanics": "Sports Biomechanics",
    "corrective_exercise": "Corrective Exercise",
    "sports_medicine": "Sports Medicine",
    "sports_nutrition": "Sports Nutrition",
}
