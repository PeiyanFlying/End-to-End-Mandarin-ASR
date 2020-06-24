""" Load and preprocess data.
"""
import torch
import glob
import torchaudio
import os
import numpy as np
import random
import torch.nn.utils.rnn as rnn_utils
import data_utils
from tqdm import tqdm
from torch.utils.data import Dataset, DataLoader
from torchnlp.samplers import BucketBatchSampler
from torchnlp.encoders.text import StaticTokenizerEncoder


class AISHELL(Dataset):
    """
    An abstract class representing a dataset. It stores file lists in __init__, and loads the FBANK features
    in __getitem__.
    """
    def __init__(self, pairs):
        """
        Args:
            pairs (list([string, string])): All of the [fbank_file, labellings] pairs.
        """
        self.pairs = pairs

    def __len__(self):
        return len(self.pairs)

    def __getitem__(self, idx):
        """
        Returns:
            x (torch.FloatTensor, [seq_length, dim_features]): The FBANK features.
            y (string): The label sequence.
        """
        path, y = self.pairs[idx]
        x = torch.load(path[:-4]+'.pth')
        return x, y

    def generateBatch(self, batch, mean, std, tokenizer):
        """
        Generate a mini-batch of data. For DataLoader's 'collate_fn'.

        Args:
            batch (list(tuple)): A mini-batch of (FBANK features, label sequences) pairs.
            mean, std (torch.FloatTensor, [dim_features]): The statistics to normalize the data.
            tokenizer (Pytorch-NLP’s StaticTokenizerEncoder): A tokenizer to encode/decode labels.

        Returns:
            xs (torch.FloatTensor, [batch_size, (padded) seq_length, dim_features]): A mini-batch of FBANK features.
            xlens (torch.LongTensor, [batch_size]): Sequence lengths before padding.
            ys (torch.LongTensor, [batch_size, (padded) n_tokens]): A mini-batch of label sequences.
        """
        xs, ys = zip(*batch)

        # normalization
        xs = [(x - mean) / std for x in xs]

        # Stack every 3 frames and down-sample frame rate by 3, following https://arxiv.org/pdf/1712.01769.pdf.
        xs = [x[:(x.shape[0]//3)*3].view(-1,3*80) for x in xs]   # [n_windows, 80] --> [n_windows//3, 240]

        xlens = torch.tensor([x.shape[0] for x in xs])

        xs = rnn_utils.pad_sequence(xs, batch_first=True)   # [batch_size, (padded) seq_length, dim_features]
        
        ys = [tokenizer.encode(y) for y in ys]
        ys = rnn_utils.pad_sequence(ys, batch_first=True)   # [batch_size, (padded) n_tokens]
        return xs, xlens, ys


def load(root, split, batch_size, workers=0):
    """
    The full process to load the data:
        1. Load the required statistical information to perform normalization and training.
        2. Create pairs of [fbank_file, labellings] examples.
        3. Build vocabulary.
        4. Create Pytorch Dataset and DataLoader.

    Args:
        root (string): The root directory of AISHELL dataset.
        split (string): Which of the subset of data to take. One of 'train', 'dev' or 'test'.
        batch_size (integer): Batch size.
        workers (integer): How many subprocesses to use for data loading.

    Returns:
        loader (DataLoader): A DataLoader can generate batches of (FBANK features, FBANK lengths, label sequence).
        tokenizer (Pytorch-NLP’s StaticTokenizerEncoder): A tokenizer to encode/decode labels.
    """
    assert split in ['train', 'dev', 'test']
    print ("Reading %s data ..." % split)

    data_train = data_utils.parse_partition(root, 'train')

    # Load statistics
    statistics = torch.load(os.path.join(root, 'statistics.pth'))
    mean = statistics['mean']
    std = statistics['std']
    xlens_train = statistics['xlens']                      # Representing {audio id: sequence length}.
    xlens_train = [xlens_train[id] for id in data_train]   # Representing [sequence length].

    # Create pairs of [fbank_file, labellings] examples.
    data_train = [[os.path.join(root, 'fbank', 'train/%s.pth'%id), data_train[id]] for id in data_train]
    assert len(xlens_train) == len(data_train)

    if split == 'train':
        data = data_train
    else:
        data = data_utils.parse_partition(root, split)
        data = [[os.path.join(root, 'fbank', '%s/%s.pth'%(split, id)), data[id]] for id in data]

    # Build vocabulary.
    tokenizer = StaticTokenizerEncoder([p[1] for p in data_train],
                                       tokenize=lambda s: ['<s>'] + list(s),
                                       min_occurrences=5,
                                       append_eos=True,
                                       reserved_tokens=['<pad>', '<unk>', '</s>'])

    # Build Pytorch DataLoaders
    dataset = AISHELL(data)
    print ("Dataset size:", len(dataset))
    
    if split == 'train':
        sampler = torch.utils.data.sampler.RandomSampler(dataset)
        batch_sampler = BucketBatchSampler(sampler,
                                           batch_size=batch_size,
                                           drop_last=False,
                                           sort_key=lambda i: xlens_train[i])
        loader = DataLoader(dataset,
                            batch_sampler=batch_sampler,
                            collate_fn=lambda batch: dataset.generateBatch(batch, mean, std, tokenizer),
                            num_workers=workers,
                            pin_memory=True)
    else:
        loader = DataLoader(dataset,
                            batch_size=batch_size,
                            shuffle=True,
                            collate_fn=lambda batch: dataset.generateBatch(batch, mean, std, tokenizer),
                            num_workers=workers,
                            pin_memory=True)
    return loader, tokenizer


def inspect_data():
    """
    Test the functionality of input pipeline and visualize a few samples.
    """
    import matplotlib.pyplot as plt

    BATCH_SIZE = 64
    SPLIT = 'dev'
    ROOT = "/data/Data2/Public-Folders/aishell/data_aishell"

    loader, tokenizer = load(ROOT, SPLIT, BATCH_SIZE)
    print ("Vocabulary size:", len(tokenizer.vocab))
    print (tokenizer.vocab[:20])

    xs, xlens, ys = next(iter(loader))
    print (xs.shape, ys.shape)
    print (xlens)
    for i in range(BATCH_SIZE):
        print (tokenizer.decode(ys[i]))
        plt.figure()
        plt.imshow(xs[i].T)
        plt.clim(-3, 12)
        plt.colorbar()
        plt.show()


if __name__ == '__main__':
    inspect_data()