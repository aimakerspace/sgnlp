import argparse
import json
from logging import error
import math
import pickle
import random
import pathlib
from typing import Dict, List, Union

import numpy as np
import torch
from transformers import PreTrainedTokenizer
from transformers.tokenization_utils_base import BatchEncoding

from data_class import SenticNetGCNTrainArgs


def parse_args_and_load_config(
    config_path: str = "config/senticnet_gcn_config.json",
) -> SenticNetGCNTrainArgs:
    """Get config from config file using argparser

    Returns:
        SenticNetGCNTrainArgs: SenticNetGCNTrainArgs instance populated from config
    """
    parser = argparse.ArgumentParser(description="SenticASGCN Training")
    parser.add_argument("--config", type=str, default=config_path)
    args = parser.parse_args()

    cfg_path = pathlib.Path(__file__).parent / args.config
    with open(cfg_path, "r") as cfg_file:
        cfg = json.load(cfg_file)

    sentic_asgcn_args = SenticNetGCNTrainArgs(**cfg)
    return sentic_asgcn_args


def set_random_seed(seed: int = 776) -> None:
    """Helper method to set random seeds for python, numpy and torch

    Args:
        seed (int, optional): seed value to set. Defaults to 776.
    """
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def load_word_vec(word_vec_file_path: str, vocab: Dict[str, int], embed_dim: int = 300) -> Dict[str, np.asarray]:
    """
    Helper method to load word vectors from file (e.g. GloVe) for each word in vocab.

    Args:
        word_vec_file_path (str): full file path to word vectors.
        vocab (Dict[str, int]): dictionary of vocab word as key and word index as values.
        embed_dim (int, optional): embedding dimension. Defaults to 300.

    Returns:
        Dict[str, np.asarray]: dictionary with words as key and word vectors as values.
    """
    with open(word_vec_file_path, "r", encoding="utf-8", newline="\n", errors="ignore") as fin:
        word_vec = {}
        for line in fin:
            tokens = line.rstrip().split()
            word, vec = " ".join(tokens[:-embed_dim]), tokens[-embed_dim:]
            if word in vocab.keys():
                word_vec[word] = np.asarray(vec, dtype="float32")
    return word_vec


def build_embedding_matrix(
    word_vec_file_path: str,
    vocab: Dict[str, int],
    embed_dim: int = 300,
    save_embed_matrix: bool = False,
    save_embed_file_path: str = None,
) -> np.ndarray:
    """
    Helper method to generate an embedding matrix.

    Args:
        word_vec_file_path (str): full file path to word vectors.
        vocab (Dict[str, int]): dictionary of vocab word as key and word index as values.
        embed_dim (int, optional): embedding dimension. Defaults to 300.
        save_embed_matrix (bool, optional): flag to indicate if . Defaults to False.
        save_embed_directory (str, optional): [description]. Defaults to None.

    Returns:
        np.array: numpy array of embedding matrix
    """
    embedding_matrix = np.zeros((len(vocab), embed_dim))
    embedding_matrix[1, :] = np.random.uniform(-1 / np.sqrt(embed_dim), 1 / np.sqrt(embed_dim), (1, embed_dim))
    word_vec = load_word_vec(word_vec_file_path, vocab, embed_dim)
    for word, idx in vocab.items():
        vec = word_vec.get(word)
        if vec is not None:
            embedding_matrix[idx] = vec

    if save_embed_matrix:
        save_file_path = pathlib.Path(save_embed_file_path)
        if not save_file_path.exists():
            save_file_path.parent.mkdir(exist_ok=True)
        with open(save_file_path, "wb") as fout:
            pickle.dump(embedding_matrix, fout)

    return embedding_matrix


class BucketIterator(object):
    """
    Bucket iterator class which provides sorting and padding for input dataset, iterate thru dataset batches
    """

    def __init__(self, data, batch_size: int, sort_key="text_indices", shuffle=True, sort=True):
        self.shuffle = shuffle
        self.sort = sort
        self.sort_key = sort_key
        self.batches = self.sort_and_pad(data, batch_size)
        self.batch_len = len(self.batches)

    def sort_and_pad(self, data, batch_size: int) -> List[Dict[str, torch.tensor]]:
        """
        Class method to sort and pad data batches

        Args:
            data (ABSADataset): input data
            batch_size (int): batch size

        Returns:
            List[Dict[str, torch.tensor]]: return a list of dictionaries of tensors
        """
        num_batch = int(math.ceil(len(data) / batch_size))
        sorted_data = sorted(data, key=lambda x: len(x[self.sort_key])) if self.sort else data
        batches = [self.pad_data(sorted_data[i * batch_size : (i + 1) * batch_size]) for i in range(num_batch)]
        return batches

    def pad_batch_encoding(self, data: BatchEncoding, max_len: int) -> BatchEncoding:
        input_ids_pad = [0] * (max_len - len(data["input_ids"]))
        token_type_ids_pad = input_ids_pad.copy()
        attention_mask_pad = [1] * (max_len - len(data["attention_mask"]))
        data["input_ids"] = torch.tensor(data["input_ids"] + input_ids_pad)
        data["token_type_ids"] = torch.tensor(data["token_type_ids"] + token_type_ids_pad)
        data["attention_mask_pad"] = torch.tensor(data["attention_mask"] + attention_mask_pad)
        return data

    def pad_data(self, batch_data: List[Dict[str, Union[BatchEncoding, int, np.ndarray]]]) -> Dict[str, torch.tensor]:
        """
        Class method to pad data batches

        Args:
            batch_data (List[Dict[str, Union[BatchEncoding, int, np.ndarray]]]): List of dictionaries containing all batches of data

        Returns:
            Dict[str, torch.tensor]: return dictionary of tensors from data batches
        """
        batch_text_indices = []
        batch_context_indices = []
        batch_aspect_indices = []
        batch_left_indices = []
        batch_polarity = []
        batch_dependency_graph = []
        batch_dependency_tree = []
        max_len = max([len(t[self.sort_key]["input_ids"]) for t in batch_data])
        # [text_indices, context_indices, aspect_indices, left_indices, polarity, dependency_graph, dependency_tree]
        for item in batch_data:
            text_indices = item["text_indices"]
            context_indices = item["context_indices"]
            aspect_indices = item["aspect_indices"]
            left_indices = item["left_indices"]
            polarity = item["polarity"]
            dependency_graph = item["dependency_graph"]
            dependency_tree = item["dependency_tree"]

            batch_text_indices.append(self.pad_batch_encoding(text_indices, max_len))
            batch_context_indices.append(self.pad_batch_encoding(context_indices, max_len))
            batch_aspect_indices.append(self.pad_batch_encoding(aspect_indices, max_len))
            batch_left_indices.append(self.pad_batch_encoding(left_indices, max_len))
            batch_polarity.append(polarity)
            batch_dependency_graph.append(
                np.pad(
                    dependency_graph,
                    (
                        (0, max_len - len(text_indices["input_ids"])),
                        (0, max_len - len(text_indices["input_ids"])),
                    ),
                    "constant",
                )
            )
            batch_dependency_tree.append(
                np.pad(
                    dependency_tree,
                    (
                        (0, max_len - len(text_indices["input_ids"])),
                        (0, max_len - len(text_indices["input_ids"])),
                    ),
                    "constant",
                )
            )
            return {
                "text_indices": batch_text_indices,
                "context_indices": batch_context_indices,
                "aspect_indices": batch_aspect_indices,
                "left_indices": batch_left_indices,
                "polarity": batch_polarity,
                "dependency_graph": torch.tensor(batch_dependency_graph),
                "dependency_tree": torch.tensor(batch_dependency_tree),
            }

    def __iter__(self):
        if self.shuffle:
            random.shuffle(self.batches)
        for idx in range(self.batch_len):
            yield self.batches[idx]


class ABSADataset(object):
    """
    Data class to hold dataset for training.
    """

    def __init__(self, data):
        self.data = data

    def __getitem__(self, index):
        return self.data[index]

    def __len__(self):
        return len(self.data)


class ABSADatasetReader:
    def __init__(
        self,
        config: SenticNetGCNTrainArgs,
        tokenizer: PreTrainedTokenizer,
    ):
        self.cfg = config
        self.tokenizer = tokenizer
        self.embedding_matrix = build_embedding_matrix(
            config.word_vec_file_path,
            tokenizer.vocab,
            config.embed_dim,
            config.save_embedding_matrix,
            config.saved_embedding_matrix_file_path,
        )
        self.train_data = ABSADataset(ABSADatasetReader.__read_data__(self.cfg.dataset_train, tokenizer))
        self.test_data = ABSADataset(ABSADatasetReader.__read_data__(self.cfg.dataset_test, tokenizer))

    @staticmethod
    def __read_data__(datasets: Dict[str, str], tokenizer: PreTrainedTokenizer):
        # Read raw data, graph data and tree data
        with open(datasets["raw"], "r", encoding="utf-8", newline="\n", errors="ignore") as fin:
            lines = fin.readlines()
        with open(datasets["graph"], "rb") as fin_graph:
            idx2graph = pickle.load(fin_graph)
        with open(datasets["tree"], "rb") as fin_tree:
            idx2tree = pickle.load(fin_tree)

        # Prep all data
        all_data = []
        for i in range(0, len(lines), 3):
            text_left, _, text_right = [s.lower().strip() for s in lines[i].partition("$T$")]
            aspect = lines[i + 1].lower().strip()
            polarity = lines[i + 2].lower().strip()
            text_indices = tokenizer(f"{text_left} {aspect} {text_right}")
            context_indices = tokenizer(f"{text_left} {text_right}")
            aspect_indices = tokenizer(aspect)
            left_indices = tokenizer(text_left)
            polarity = int(polarity) + 1
            dependency_graph = idx2graph[i]
            dependency_tree = idx2tree[i]

            data = {
                "text_indices": text_indices,
                "context_indices": context_indices,
                "aspect_indices": aspect_indices,
                "left_indices": left_indices,
                "polarity": polarity,
                "dependency_graph": dependency_graph,
                "dependency_tree": dependency_tree,
            }
            all_data.append(data)
        return all_data