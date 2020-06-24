""" Compute phoneme error rate (PER).
"""
import torch
import os
import argparse
import eval_utils


def main():
    parser = argparse.ArgumentParser(description="Compute phoneme error rate (PER).")
    parser.add_argument('ckpt', type=str, help="Checkpoint to restore.")
    parser.add_argument('--split', default='test', type=str, help="Specify which split of data to evaluate.")
    parser.add_argument('--gpu_id', default=0, type=int, help="CUDA visible GPU ID. Currently only support single GPU.")
    parser.add_argument('--root', default="data/lisa/data/timit/raw/TIMIT", type=str, help="Directory of dataset.")
    args = parser.parse_args()

    os.environ["CUDA_VISIBLE_DEVICES"] = str(args.gpu_id)
    assert torch.cuda.is_available()
    import data
    import build_model

    # Restore checkpoint
    info = torch.load(args.ckpt)
    print ("Dev PER of checkpoint: %.4f @epoch: %d" % (info['dev_per'], info['epoch']))

    cfg = info['cfg']

    # Create dataset
    loader, tokenizer = data.prepareData(root=args.root,
                                         split=args.split,
                                         batch_size=cfg['train']['batch_size'])

    # Build model
    model = build_model.Seq2Seq(len(tokenizer.vocab),
                                hidden_size=cfg['model']['hidden_size'],
                                encoder_layers=cfg['model']['encoder_layers'],
                                decoder_layers=cfg['model']['decoder_layers'])
    model.load_state_dict(info['weights'])
    model.eval()
    model = model.cuda()

    # Evaluate
    per = eval_utils.get_per(loader, model, tokenizer.vocab)
    print ("PER on %s set = %.4f" % (args.split, per))


if __name__ == '__main__':
    main()
