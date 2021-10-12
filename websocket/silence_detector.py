#  Copyright (c) 2020 Dmitrii Borisov
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in all
#  copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#  SOFTWARE.
LITTLE_ENDIAN = 0
BIG_ENDIAN = 1
SIGNED16BIT = 2
FQ8000HZ = 3


class SilenceDetector:

    def __init__(self, frequency: int, sample_format: int, byteorder: int, volume_level: float = 0.0,
                 volume_length: int = 150, init_silence_length: int = 500, silence_length: int = 400,
                 silence_to_volume_level: float = 0.01):
        """
        @volume_length   - int, total count milliseconds of volume after which object will start to found a silence
        @init_silence_length  - int, total count milliseconds of silence for volume level detection
        @silence_length  - int, total count milliseconds of silence after which object.get_silence will return True
        @silence_to_volume_level - float, the ratio of the areas under the module of the sound curve in the silence
                                   section to the voice section
        @frequency       - raw format parameter (8000, 16000, 24000, 48000 etc), must be set as constants
        @sample_format   - raw format parameter (8bit, 16 bit, signed/unsigned int, float, etc), must be set as
                           constant
        """
        self._init_silence_length = init_silence_length
        self._silence_length = silence_length
        self._volume_length = volume_length
        self._diff = silence_to_volume_level
        if volume_level:
            self._volume_level = volume_level
        else:
            self._volume_level = 0

        if frequency == FQ8000HZ:
            self._freq = 8000
            self._period = 1 / 8000
        if sample_format == SIGNED16BIT:
            self._sample_len = 2
            self._signed = True
        # todo add other formats there
        if byteorder == LITTLE_ENDIAN:
            self._byte_order = 'little'
        elif byteorder == BIG_ENDIAN:
            self._byte_order = 'big'
        self._data = bytes()
        self._volume_detected = False
        self._silence_detected = False

    def _store_chunk(self, chunk):
        """
        private method for storing new chunks, can be different for persistent/non persistent audio storages
        """
        self._data += chunk

    def _get_sound_square(self, chunk: bytes) -> float:
        res = 0.0
        for i in range(0, len(chunk), self._sample_len):
            res += abs(int.from_bytes(chunk[i:i + self._sample_len], self._byte_order, signed=self._signed))
        return res

    def _get_sound_level(self, chunk) -> float:
        return self._get_sound_square(chunk) / self._get_chunk_len(chunk)

    def _get_chunk_len(self, chunk: bytes) -> float:
        return float(len(chunk)) / self._sample_len * self._period

    def _get_data_len(self) -> float:
        return self._get_chunk_len(self._data)

    def get_silence(self, chunk) -> bool:
        self._store_chunk(chunk)

        if not self._volume_level and self._get_data_len() * 1000 < self._volume_length + self._init_silence_length:
            # we don't have enough data for detection
            return False

        if not self._volume_level:
            silence_candidate_start = -int(self._init_silence_length * self._sample_len * self._freq / 1000)
            silence_candidate_level = self._get_sound_level(self._data[silence_candidate_start:])
            volume_candidate_start = -int(
                (self._volume_length + self._init_silence_length) / 1000 * self._sample_len / self._period)
            volume_candidate_level = self._get_sound_level(self._data[volume_candidate_start:silence_candidate_start])
            if volume_candidate_level > 0:
                volume_level = silence_candidate_level / volume_candidate_level
                if volume_level < self._diff:
                    self._volume_level = volume_candidate_level
                    self._silence_detected = True
        else:
            silence_candidate_start = -int(self._silence_length * self._freq * self._sample_len / 1000)
            silence_candidate_level = self._get_sound_level(self._data[silence_candidate_start:])
            volume_level = silence_candidate_level / self._volume_level
            if volume_level < self._diff:
                self._silence_detected = True
                self._volume_detected = False
            else:
                self._silence_detected = False
                self._volume_detected = True

        return self._silence_detected

    def is_new_silence(self, chunk) -> bool:
        silence_before = self._silence_detected
        return self.get_silence(chunk) and not silence_before
