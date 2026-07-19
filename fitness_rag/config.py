from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "fitness_mock_3000.jsonl"
SPLIT_PATH = ROOT / "artifacts" / "dataset_split.json"
METRICS_PATH = ROOT / "artifacts" / "evaluation_metrics.json"
DB_PATH = ROOT / "fitness_vector_db_final"

APP_NAME = "RAG-Rumor Smasher"
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
