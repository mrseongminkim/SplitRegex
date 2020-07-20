from __future__ import print_function, division

import torch
import torchtext

import seq2seq
from seq2seq.loss import NLLLoss
from seq2seq.util.string_preprocess import pad_tensor

class Evaluator(object):
    """ Class to evaluate models with given datasets.

    Args:
        loss (seq2seq.loss, optional): loss for evaluator (default: seq2seq.loss.NLLLoss)
        batch_size (int, optional): batch size for evaluator (default: 64)
    """

    def __init__(self, loss=NLLLoss(), batch_size=64, input_vocab=None):
        self.loss = loss
        self.batch_size = batch_size
        self.input_vocab = input_vocab
        
    def evaluate(self, model, data):
        """ Evaluate a model on given dataset and return performance.

        Args:
            model (seq2seq.models): model to evaluate
            data (seq2seq.dataset.dataset.Dataset): dataset to evaluate against

        Returns:
            loss (float): loss of the given model on the given dataset
        """
        model.eval()

        loss = self.loss
        loss.reset()
        match = 0
        total = 0

        device = torch.device('cuda:0') if torch.cuda.is_available() else -1
        batch_iterator = torchtext.data.BucketIterator(
            dataset=data, batch_size=self.batch_size,
            sort=False, sort_within_batch=False,
            device=device, repeat=False, shuffle=True, train=False)
        
        tgt_vocab = data.fields[seq2seq.tgt_field_name].vocab
        pad = tgt_vocab.stoi[data.fields[seq2seq.tgt_field_name].pad_token]

        with torch.no_grad():
            for batch in batch_iterator:
                target_variables = getattr(batch, seq2seq.tgt_field_name)

                pos_input_variables = [[] for i in range(batch.batch_size)]
                pos_input_lengths = [[] for i in range(batch.batch_size)]
                
                neg_input_variables = [[] for i in range(batch.batch_size)]
                neg_input_lengths = [[] for i in range(batch.batch_size)]
                
                set_size = len(batch.fields)-1
                max_len_within_batch = -1
                
                for idx in range(batch.batch_size):
                    for src_idx in range(1, int(set_size/2)+1):
                        src, src_len = getattr(batch, 'pos{}'.format(src_idx))
                        pos_input_variables[idx].append(src[idx])
                        pos_input_lengths[idx].append(src_len[idx])
                    
                    for src_idx in range(1, int(set_size/2)+1):
                        src, src_len = getattr(batch, 'neg{}'.format(src_idx))
                        neg_input_variables[idx].append(src[idx])
                        neg_input_lengths[idx].append(src_len[idx])
                    
                    pos_input_lengths[idx] = torch.stack(pos_input_lengths[idx], dim =0)
                    neg_input_lengths[idx] = torch.stack(neg_input_lengths[idx], dim =0)
                    
                    if max_len_within_batch <  torch.max(pos_input_lengths[idx].view(-1)).item():
                        max_len_within_batch = torch.max(pos_input_lengths[idx].view(-1)).item()
                    
                    if max_len_within_batch <  torch.max(neg_input_lengths[idx].view(-1)).item():
                        max_len_within_batch = torch.max(neg_input_lengths[idx].view(-1)).item()

                for batch_idx in range(len(pos_input_variables)):
                    for set_idx in range(int(set_size/2)):
                        pos_input_variables[batch_idx][set_idx] = pad_tensor(pos_input_variables[batch_idx][set_idx], 
                                                                         max_len_within_batch, self.input_vocab)
                        
                        neg_input_variables[batch_idx][set_idx] = pad_tensor(neg_input_variables[batch_idx][set_idx], 
                                                                         max_len_within_batch, self.input_vocab)
                        
                    pos_input_variables[batch_idx] = torch.stack(pos_input_variables[batch_idx], dim=0)
                    neg_input_variables[batch_idx] = torch.stack(neg_input_variables[batch_idx], dim=0)

                
                pos_input_variables = torch.stack(pos_input_variables, dim=0)
                pos_input_lengths = torch.stack(pos_input_lengths, dim=0)
                
                neg_input_variables = torch.stack(neg_input_variables, dim=0)
                neg_input_lengths = torch.stack(neg_input_lengths, dim=0)
                
                input_variables = (pos_input_variables, neg_input_variables)
                input_lengths= (pos_input_lengths, neg_input_lengths)

                decoder_outputs, decoder_hidden, other = model(input_variables, input_lengths, target_variables)

                # Evaluation
                seqlist = other['sequence']
                for step, step_output in enumerate(decoder_outputs):
                    target = target_variables[:, step + 1]
                    loss.eval_batch(step_output.view(target_variables.size(0), -1), target)

                    non_padding = target.ne(pad)
                    correct = seqlist[step].view(-1).eq(target).masked_select(non_padding).sum().item()
                    match += correct
                    total += non_padding.sum().item()

        if total == 0:
            accuracy = float('nan')
        else:
            accuracy = match / total

        return loss.get_loss(), accuracy
