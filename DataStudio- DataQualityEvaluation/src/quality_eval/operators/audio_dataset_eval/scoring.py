from quality_eval.operators.image_dataset_eval.scoring import ImageDatasetScoreOperator


class AudioDatasetScoreOperator(ImageDatasetScoreOperator):
    operator_name: str = "audio_dataset_score"
