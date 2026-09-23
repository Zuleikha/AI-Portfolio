"""Hugging Face datasets integration"""

from datasets import DatasetDict, load_dataset


class HuggingFaceDatasetConfig:
    """Configuration for Hugging Face datasets

    The default is the ADE Corpus V2 adverse-drug-event classification set: binary
    sentence classification over MEDLINE case reports, already carrying ``text`` and
    ``label`` columns and a train/test split. The ``SetFit`` mirror is used rather
    than ``ade-benchmark-corpus/ade_corpus_v2`` because the canonical repository
    ships a single ``train`` split, and this pipeline requires ``test`` to exist.
    """

    def __init__(
        self,
        dataset_name="SetFit/ade_corpus_v2_classification",
        subset=None,
        sample_size=None,
    ):
        self.dataset_name = dataset_name
        self.subset = subset
        self.sample_size = sample_size
        self.text_column = "text"
        self.label_column = "label"


class HuggingFaceDatasetManager:
    """Manage Hugging Face datasets for ML pipeline"""

    def __init__(self, config):
        self.config = config
        self.dataset = None

    def load_dataset_from_hub(self):
        """Load dataset from Hugging Face Hub"""
        if self.config.subset:
            dataset = load_dataset(self.config.dataset_name, self.config.subset)
        else:
            dataset = load_dataset(self.config.dataset_name)

        # Sample data if specified
        if self.config.sample_size:
            sampled_dataset = {}
            for split_name in dataset:
                if len(dataset[split_name]) > self.config.sample_size:
                    sampled_dataset[split_name] = dataset[split_name].select(
                        range(self.config.sample_size)
                    )
                else:
                    sampled_dataset[split_name] = dataset[split_name]
            dataset = DatasetDict(sampled_dataset)

        self.dataset = dataset
        return dataset
