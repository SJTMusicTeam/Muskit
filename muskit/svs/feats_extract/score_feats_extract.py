import logging
from typing import Any
from typing import Dict
from typing import Optional
from typing import Tuple
from typing import Union

import humanfriendly
import torch
from typeguard import check_argument_types

from muskit.torch_utils.nets_utils import make_pad_mask
from muskit.layers.stft import Stft
from muskit.svs.feats_extract.abs_feats_extract import AbsFeatsExtract

def ListsToTensor(xs):
    max_len = max(len(x) for x in xs)
    ys = []
    for x in xs:
        y = x + [0]*(max_len - len(x))
        ys.append(y)
    return ys

class FrameLabelAggregate(AbsFeatsExtract):
    def __init__(
        self,
        fs: Union[int, str] = 22050,
        n_fft: int = 1024,
        win_length: int = 512,
        hop_length: int = 128,
        window: str = "hann",
        center: bool = True,
        ftype: str = "frame",  # syllable
    ):
        assert check_argument_types()
        super().__init__()

        self.fs = fs
        self.n_fft = n_fft
        self.win_length = win_length
        self.hop_length = hop_length
        self.window = window
        self.center = center
        self.ftype = ftype

    def extra_repr(self):
        return (
            f"win_length={self.win_length}, "
            f"hop_length={self.hop_length}, "
            f"center={self.center}, "
            f"ftype={self.ftype}, "
        )

    def output_size(self) -> int:
        return 1

    def get_parameters(self) -> Dict[str, Any]:
        return dict(
            fs=self.fs,
            n_fft=self.n_fft,
            hop_length=self.hop_length,
            window=self.window,
            win_length=self.win_length,
            center=self.stft.center,
            # normalized=self.stft.normalized,
            # use_token_averaged_energy=self.use_token_averaged_energy,
            # reduction_factor=self.reduction_factor,
        )

    def forward(
        self, input: torch.Tensor, input_lengths: torch.Tensor = None
    ) -> Tuple[torch.Tensor, Optional[torch.Tensor]]:
        """LabelAggregate forward function.
        Args:
            input: (Batch, Nsamples, Label_dim)
            input_lengths: (Batch)
        Returns:
            output: (Batch, Frames, Label_dim)
        """
        bs = input.size(0)
        max_length = input.size(1)
        label_dim = input.size(2)

        # NOTE(jiatong):
        #   The default behaviour of label aggregation is compatible with
        #   torch.stft about framing and padding.

        # Step1: center padding
        if self.center:
            pad = self.win_length // 2
            max_length = max_length + 2 * pad
            input = torch.nn.functional.pad(input, (0, 0, pad, pad), "constant", 0)
            input[:, :pad, :] = input[:, pad : (2 * pad), :]
            input[:, (max_length - pad) : max_length, :] = input[
                :, (max_length - 2 * pad) : (max_length - pad), :
            ]
            nframe = (max_length - self.win_length) // self.hop_length + 1

        # Step2: framing
        output = input.as_strided(
            (bs, nframe, self.win_length, label_dim),
            (max_length * label_dim, self.hop_length * label_dim, label_dim, 1),
        )

        # Step3: aggregate label
        # (bs, nframe, self.win_length, label_dim) => (bs, nframe)
        output, _ = output.sum(dim=2, keepdim=False).mode(dim=-1, keepdim=False)

        # Step4: process lengths
        if input_lengths is not None:
            if self.center:
                pad = self.win_length // 2
                input_lengths = input_lengths + 2 * pad

            olens = (input_lengths - self.win_length) // self.hop_length + 1
            output.masked_fill_(make_pad_mask(olens, output, 1), 0.0)
        else:
            olens = None

        return output, olens

    def get_segments(self,
        durations: Optional[torch.Tensor] = None,
        durations_lengths: Optional[torch.Tensor] = None,
        score: Optional[torch.Tensor] = None,
        score_lengths: Optional[torch.Tensor] = None,
        tempo: Optional[torch.Tensor] = None,
        tempo_lengths: Optional[torch.Tensor] = None,):
        seq = [0]
        for i in range(durations_lengths):
            if durations[ seq[-1] ] != durations[i]:
                seq.append(i)
        
        seq.append(durations_lengths.item())
        
        seq.append(0)
        for i in range(score_lengths):
            if score[ seq[-1] ] != score[i]:
                seq.append(i)
        seq.append(score_lengths.item())
        seq = list(set(seq))
        seq.sort()

        lengths = len(seq) - 1
        seg_duartion = []#torch.zeros(lengths, dtype=torch.long)
        seg_score = []#torch.zeros(lengths, dtype=torch.long)
        seg_tempo = []#torch.zeros(lengths, dtype=torch.long)
        for i in range(lengths):
            l, r = seq[i], seq[i + 1]
            tmp_duartion, _ = durations[l:r].mode()
            tmp_score, _ = score[l:r].mode()
            tmp_tempo, _ = tempo[l:r].mode()
            seg_duartion.append(tmp_duartion.item())
            seg_score.append(tmp_score.item())
            seg_tempo.append(tmp_tempo.item())
        return seg_duartion, lengths, seg_score, lengths, seg_tempo, lengths        

    def syllable_forward(
        self, 
        durations: Optional[torch.Tensor] = None,
        durations_lengths: Optional[torch.Tensor] = None,
        score: Optional[torch.Tensor] = None,
        score_lengths: Optional[torch.Tensor] = None,
        tempo: Optional[torch.Tensor] = None,
        tempo_lengths: Optional[torch.Tensor] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor, \
                torch.Tensor, torch.Tensor, \
                torch.Tensor, torch.Tensor]:
        """LabelAggregate forward function.
        Args:
            durations: (Batch, Nsamples)
            durations_lengths: (Batch)
            score: (Batch, Nsamples)
            score_lengths: (Batch)
            tempo: (Batch, Nsamples)
            tempo_lengths: (Batch)
        Returns:
            output: (Batch, Frames)
        """
        # logging.info(f'durations.shape:{durations.shape}')
        # logging.info(f'score.shape:{score.shape}')
        # logging.info(f'tempo.shape:{tempo.shape}')
        # logging.info(f'durations_lengths.shape:{durations_lengths.shape}')
        # logging.info(f'score_lengths.shape:{score_lengths.shape}')
        # logging.info(f'tempo_lengths.shape:{tempo_lengths.shape}')
        assert durations.shape == score.shape and score.shape == tempo.shape
        assert durations_lengths.shape == score_lengths.shape  and score_lengths.shape == tempo_lengths.shape
        
        bs = durations.size(0)
        seg_durations, seg_durations_lengths = [], []
        seg_score, seg_score_lengths = [], []
        seg_tempo, seg_tempo_lengths = [], []

        for i in range(bs):
            seg = self.get_segments(durations=durations[i], \
                                    durations_lengths=durations_lengths[i], \
                                    score=score[i], \
                                    score_lengths=score_lengths[i],\
                                    tempo=tempo[i],\
                                    tempo_lengths=tempo_lengths[i])
            seg_durations.append(seg[0])
            seg_durations_lengths.append(seg[1])
            seg_score.append(seg[2])
            seg_score_lengths.append(seg[3])
            seg_tempo.append(seg[4])
            seg_tempo_lengths.append(seg[5])
        
        seg_durations = torch.LongTensor(ListsToTensor(seg_durations))
        seg_durations_lengths = torch.LongTensor(seg_durations_lengths)
        seg_score = torch.LongTensor(ListsToTensor(seg_score))
        seg_score_lengths = torch.LongTensor(seg_score_lengths)
        seg_tempo = torch.LongTensor(ListsToTensor(seg_tempo))
        seg_tempo_lengths = torch.LongTensor(seg_tempo_lengths)

        return seg_durations, seg_durations_lengths, \
                seg_score, seg_score_lengths, \
                seg_tempo, seg_tempo_lengths

