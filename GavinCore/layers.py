import typing
from typing import List
from tensorflow.python.keras.utils import tf_utils

from .utils import tf
from typing import Dict


def iid_gaussian(m, d):
    """Generate random values that are I.I.D (independent identically distributed)
    :param m: int
        Hidden Dimensions
    :param d: int
        Depth (half the hidden dimensions)"""
    return tf.random.normal(shape=(m, d))


def orthogonal_gaussian(m: int, d: int):
    """Generate Orthogonal Gaussian distribution's. This is to improve upon MSE (mean squared error)
    inside a performer.
    Args:
        :param m: int
            Hidden Dimensions
        :param d: int
            Depth (half the hidden dimensions)"""

    def orthogonal_square():
        q, _ = tf.linalg.qr(iid_gaussian(d, d))
        return tf.transpose(q)

    num_squares = int(m / d)
    blocks = [orthogonal_square() for _ in range(num_squares)]

    remainder = m - d * num_squares
    if remainder:
        blocks.append(orthogonal_square()[:remainder])

    # matrix = tf.concat(blocks, axis=0)
    matrix = tf.experimental.numpy.vstack(blocks)
    matrix /= tf.sqrt(num_squares + remainder / d)

    return matrix


def softmax_kernel_transformation(data: tf.Tensor,
                                  is_query: bool,
                                  projection_matrix: tf.Tensor = None,
                                  numerical_stabilizer=0.000001):
    """Computes random features for the softmax kernel using FAVOR+ mechanism.

  Computes random features for the softmax kernel using FAVOR+ mechanism from
  https://arxiv.org/pdf/2009.14794.pdf.

  Args:
    :param data: tf.Tensor
        input data tensor of the shape [B, L, H, D], where: B - batch dimension,
            L - attention dimensions, H - heads, D - depth
    :param is_query: tf.Tensor
        Indicates whether input data is a query oor key tensor
    :param projection_matrix: tf.Tensor
        random Gaussian matrix of shape [M, D], where M stands for the
        number of random features and each D x D sub-block has pairwise orthogonal rows
    :param numerical_stabilizer: float
        small positive constant for numerical stability.

  Returns:
    Corresponding kernel feature map.
  """
    projection_matrix = tf.cast(projection_matrix, data.dtype)
    data_normalizer = 1.0 / (
        tf.math.sqrt(tf.math.sqrt(tf.dtypes.cast(tf.shape(data)[-1], data.dtype))))
    data = data_normalizer * data
    ratio = 1.0 / tf.math.sqrt(
        tf.dtypes.cast(tf.shape(projection_matrix)[0], data.dtype))
    # noinspection SpellCheckingInspection
    data_dash = tf.einsum("blhd,md->blhm", data, projection_matrix, name="SoftmaxKernel")
    diag_data = tf.math.square(data)
    diag_data = tf.math.reduce_sum(
        diag_data, axis=tf.keras.backend.ndim(data) - 1)
    diag_data = diag_data / 2.0
    diag_data = tf.expand_dims(diag_data, axis=tf.keras.backend.ndim(data) - 1)
    last_dims_t = (tf.rank(data_dash) - 1,)
    attention_dims_t = (tf.rank(data_dash) - 3,)
    if is_query:
        data_dash = ratio * (
                tf.math.exp(data_dash - diag_data - tf.math.reduce_max(
                    data_dash, axis=last_dims_t, keepdims=True)) + numerical_stabilizer)
    else:
        data_dash = ratio * (
                tf.math.exp(data_dash - diag_data - tf.math.reduce_max(
                    data_dash, axis=last_dims_t + attention_dims_t, keepdims=True)) +
                numerical_stabilizer)

    return data_dash


def relu_kernel_transformation(data: tf.Tensor,
                               projection_matrix: tf.Tensor = None,
                               numerical_stabilizer=0.000001):
    """Computes random features for the ReLU kernel using FAVOR+ mechanism.

    Args:
        :param data: tf.Tensor
            input data tensor of the shape [B, L, H, D], where: B - batch dimension,
            L - attention dimensions, H - heads, D - depth
        :param projection_matrix: tf.Tensor
            random Gaussian matrix of shape [M, D], where M stands for the
            number of random features and each D x D sub-block has pairwise orthogonal rows
        :param numerical_stabilizer: float
            small positive constant for numerical stability.
    """
    projection_matrix = tf.cast(projection_matrix, data.dtype)
    m = tf.shape(data)[-1]
    m = tf.cast(m, data.dtype)
    data_normalizer = 1.0 / tf.math.sqrt(m)
    projection_matmul = tf.einsum("blhd,md->blhm", data, projection_matrix)
    return tf.nn.relu(data_normalizer * projection_matmul + numerical_stabilizer)


def attn_hat(query: tf.Tensor, key: tf.Tensor, value: tf.Tensor, phi_fun=None, random_feats: tf.Tensor = None):
    """
    Args:
        :param query: tf.Tensor
            The Query tensor from the Multi-headed attention mechanism
        :param key: tf.Tensor
        The Key tensor from the Multi-headed attention mechanism
        :param value: tf.Tensor
            The Value tensor from the Multi-headed attention mechanism
        :param phi_fun: Any function
            A function for "phi" If None, default to Softmax kernel transformations
        :param random_feats: tf.Tensor
            The random features for use in phi function in predicting the softmax values
    """
    sequence_length = tf.shape(query)[2]
    # B, H, L, D to B, L, H, D
    query = tf.transpose(query, [0, 2, 1, 3])
    key = tf.transpose(key, [0, 2, 1, 3])
    if phi_fun is not None:
        q_prime = phi_fun(query, random_feats)
        k_prime = phi_fun(key, random_feats)
    else:
        q_prime = softmax_kernel_transformation(query, projection_matrix=random_feats, is_query=True)  # B L H M
        k_prime = softmax_kernel_transformation(key, projection_matrix=random_feats, is_query=False)  # B L H M

    # B H L D, L B H D
    value = tf.transpose(value, [2, 0, 1, 3])

    # B L H M, L B H M
    k_prime = tf.transpose(k_prime, [1, 0, 2, 3])  # L B H M
    q_prime = tf.transpose(q_prime, [1, 0, 2, 3])  # L B H M

    # noinspection SpellCheckingInspection
    av_attention = tf.einsum("lbhm,lbhd->bhmd", k_prime, value, name="AVAttention_PA")

    # noinspection SpellCheckingInspection
    av_attention = tf.einsum("lbhm,bhmd->lbhd", q_prime, av_attention, name="AVAttention_PB")
    # noinspection SpellCheckingInspection
    normalizer = tf.einsum("lbhm,l->bhm", k_prime, tf.ones(sequence_length, dtype=k_prime.dtype), name="NormalizerPA")
    # noinspection SpellCheckingInspection
    normalizer = tf.einsum("lbhm,bhm->lbh", q_prime, normalizer, name="NormalizerPB")
    av_attention = tf.transpose(av_attention, [1, 0, 2, 3])  # B L H D
    normalizer = tf.transpose(normalizer, [1, 0, 2])  # B L H
    normalizer = tf.expand_dims(normalizer, tf.rank(normalizer))  # B L H 1
    return av_attention / normalizer


def positive_attention(query: tf.Tensor, key: tf.Tensor, value: tf.Tensor, random_feats: tf.Tensor):
    """Instead of using ScaledDotProduction, this uses the above Gaussian elements to estimate the answer that
    the full ScaledDotProduction would give.
    Args:
        :param query: tf.Tensor
            The Query tensor from the Multi-headed attention mechanism
        :param key: tf.Tensor
            The Key tensor from the Multi-headed attention mechanism
        :param value:
            The Value tensor from the Multi-headed attention mechanism
        :param random_feats:
            The random features for use in phi function in predicting the softmax values.
        """

    return attn_hat(query, key, value, random_feats=random_feats)


def positive_relu_attention(query: tf.Tensor, key: tf.Tensor, value: tf.Tensor, random_feats: tf.Tensor):
    """Instead of using ScaledDotProduction, this uses the above Gaussian elements to estimate the answer that
    the full ScaledDotProduction would give.
    Args:
        :param query: tf.Tensor
            The Query tensor from the Multi-headed attention mechanism
        :param key: tf.Tensor
            The Key tensor from the Multi-headed attention mechanism
        :param value:
            The Value tensor from the Multi-headed attention mechanism
        :param random_feats:
            The random features for use in phi function in predicting the softmax values.
        """

    return attn_hat(query, key, value, random_feats=random_feats, phi_fun=relu_kernel_transformation)


def scaled_dot_product_attention(query: tf.Tensor, key: tf.Tensor, value: tf.Tensor, mask: tf.Tensor, name_prefix: str) -> typing.Tuple[tf.Tensor, tf.Tensor]:
    """
    Args:
        :param query: tf.Tensor
            The Query tensor from the Multi-headed attention mechanism
        :param key: tf.Tensor
            The Key tensor from the Multi-headed attention mechanism
        :param value: tf.Tensor
            The Value tensor from the Multi-headed attention mechanism
        :param mask: tf.Tensor
            For masking out previous outputs
        :param name_prefix: str
            The name prefix for the attention mechanism
    :return: The final tensor object
    """
    matmul_qk = tf.matmul(query, key, transpose_b=True)

    depth = tf.cast(tf.shape(key)[-1], query.dtype)
    logits = matmul_qk / tf.math.sqrt(depth)
    logits = tf.cast(logits, tf.float32)

    # add the mask zero out padding tokens.
    if mask is not None:
        logits += (tf.cast(mask, tf.float32) * -1e9)

    attention_weights = tf.nn.softmax(logits, axis=-1, name=name_prefix + "_attention_weights")
    return tf.cast(tf.matmul(attention_weights, tf.cast(value, tf.float32)), query.dtype), attention_weights


@tf.keras.utils.register_keras_serializable('GavinCore')
class FourierTransformationLayer(tf.keras.layers.Layer):
    """
    From the paper: https://arxiv.org/pdf/2105.03824.pdf
    Fourier transformations can apparently be used in attention & achieve similar results.
    Applies FFT1D across the first dimension of the embeddings (sequence_length).
    Applies FFT2D across the last two dimensions of the embeddings (sequence_length, d_model).
    Furthermore, applies FFT1D across the last dimension of the embeddings (d_model).

    """

    def __init__(self, name="fourier_transformation", *args, **kwargs):
        super(FourierTransformationLayer, self).__init__(name=name, *args, **kwargs)

    @staticmethod
    def call(inputs: tf.Tensor):
        """
        Args:
            :param inputs: tf.Tensor
                The input tensor to be transformed. Should be of shape (batch_size, sequence_length, d_model)
        :return: tf.Tensor
            The transformed tensor. Should be of shape (batch_size, sequence_length, d_model)
        """
        output = tf.cast(inputs, tf.complex64)
        output = tf.signal.fft2d(output)
        # output = tf.signal.fft(output)
        # output = tf.signal.fft(output)
        return tf.cast(output, inputs.dtype)


@tf.keras.utils.register_keras_serializable('GavinCore')
# noinspection PyMethodOverriding,PyMethodMayBeStatic
class PositionalEncoding(tf.keras.layers.Layer):
    """Positional Encoding

    Acts as input for the model, attention to where words appear in an input etc...

    Attributes:
        :param position: int
            The position the word appears in
        :param d_model: int
            This is for the attention math, acts as units for other layers in the model too.
    """

    def __init__(self, position: int, d_model: int, **kwargs):
        self.d_model = d_model
        self.position = position
        super(PositionalEncoding, self).__init__(**kwargs)
        self.pos_encoding = self.positional_encoding(position, d_model=d_model)

    def get_angles(self, position: int, i, d_model: int):
        angles = 1 / tf.pow(10000, (2 * (i // 2)) / tf.cast(d_model, tf.float32))
        return position * angles

    def positional_encoding(self, position, d_model):
        angle_rads = self.get_angles(
            position=tf.range(position, dtype=tf.float32)[:, tf.newaxis],
            i=tf.range(d_model, dtype=tf.float32)[tf.newaxis, :],
            d_model=d_model)

        # apply sin to even index in the array
        sines = tf.math.sin(angle_rads[:, 0::2])
        # apply cos to odd index in the array
        cosines = tf.math.cos(angle_rads[:, 1::2])

        pos_encoding = tf.concat([sines, cosines], axis=-1)
        pos_encoding = pos_encoding[tf.newaxis, ...]
        return tf.cast(pos_encoding, tf.float32)

    def call(self, inputs):
        y = self.pos_encoding[:, :tf.shape(inputs)[1], :]
        y = tf.cast(y, inputs.dtype)
        return inputs + y

    def get_config(self):
        cfg = {'d_model': self.d_model,
               'position': self.position}
        return cfg


@tf.keras.utils.register_keras_serializable('GavinCore')
class RotaryPositionalEncoding(tf.keras.layers.Layer):
    """Rotary Positional Encoding
    This kind of positional encoding is used by the GPT-J model, its an alternative to the standard positional encoding
    which is used in the Transformer model. This positional encoding works by adding a sinusoidal signal to the input
    embeddings at the positional positions.
    """

    def __init__(self, name: str = "rotary_positional_encoding", **kwargs):
        super(RotaryPositionalEncoding, self).__init__(name=name, **kwargs)

    @staticmethod
    def align(tensor, axes: List[int], ndim=None):
        """
        https://github.com/bojone/bert4keras/blob/70a7eb9ace18b9f4806b6386e5183f32d024bc37/bert4keras/backend.py#L136
        """
        ndim = ndim or max(axes) + 1
        indices = [None] * ndim
        for i in axes:
            indices[i] = slice(None)
        return tensor[indices]

    @staticmethod
    def check_n(inputs: tf.Tensor):
        return tf.cond(pred=tf.equal(tf.rank(inputs), 4), true_fn=lambda: 3, false_fn=lambda: 0)

    def call(self, inputs):
        n = self.check_n(inputs)
        sinusoidal = self.align(inputs[n], axes=[0, 1, -1], ndim=tf.keras.backend.ndim(inputs[0]))
        cos_pos = tf.keras.backend.repeat_elements(sinusoidal[..., 1::2], 2, -1)
        sin_pos = tf.keras.backend.repeat_elements(sinusoidal[..., ::2], 2, -1)
        return inputs * cos_pos + inputs * sin_pos

    def get_config(self):
        return {}


@tf.keras.utils.register_keras_serializable('GavinCore')
# noinspection PyMethodOverriding,PyShadowingNames
class GavinMultiHeadAttention(tf.keras.layers.Layer):
    # noinspection Assert
    def __init__(self, d_model: int, num_heads: int, name: str = "multi_head_attention", **kwargs):
        """Multi Head Attention Layer

        ...
        Attributes:
            :param d_model: int
                Embeddings Size
            :param num_heads: int
                The number of heads the layer should have
            :param name: str
                The name of layer
        """
        super(GavinMultiHeadAttention, self).__init__(name=name)
        self.num_heads = num_heads
        self.d_model = d_model

        assert d_model % self.num_heads == 0

        self.depth = d_model // self.num_heads

        self.query_dense = tf.keras.layers.Dense(units=d_model)
        self.key_dense = tf.keras.layers.Dense(units=d_model)
        self.value_dense = tf.keras.layers.Dense(units=d_model)
        self.saved_attention_image = None

        self.dense = tf.keras.layers.Dense(units=d_model)
        super(GavinMultiHeadAttention, self).__init__(**kwargs)

    def split_heads(self, inputs, batch_size: int):
        inputs = tf.reshape(inputs, shape=(batch_size, -1, self.num_heads, self.depth))  # B, L, H, D
        return tf.transpose(inputs, perm=[0, 2, 1, 3])  # B, H, L, D

    def call(self, inputs: Dict):
        query, key, value, mask = (inputs['query'], inputs['key'],
                                   inputs['value'], inputs['mask'])
        batch_size = tf.shape(query)[0]

        # linear layers
        query = self.query_dense(query)
        key = self.key_dense(key)
        value = self.value_dense(value)

        # split heads
        query = self.split_heads(query, batch_size)
        key = self.split_heads(key, batch_size)
        value = self.split_heads(value, batch_size)

        scaled_attention, attention_matrix = scaled_dot_product_attention(query, key, value, mask, name_prefix=self.name)
        self.saved_attention_image = attention_matrix

        scaled_attention = tf.transpose(scaled_attention, perm=[0, 2, 1, 3])

        concat_attention = tf.reshape(scaled_attention,
                                      (batch_size, -1, self.d_model))

        outputs = self.dense(concat_attention)

        return outputs

    def get_config(self):
        cfg = {'d_model': self.d_model,
               'num_heads': self.num_heads}
        return cfg


@tf.keras.utils.register_keras_serializable('GavinCore')
class GavinMultiHeadPerformerAttention(GavinMultiHeadAttention):
    """MultiHead attention using the performers' specification,
    significantly improving memory and time complexity allowing for
    higher values of sequence length, whilst maintaining as good or
    some cases better accuracy compared to standard transformer.

    Attributes:
        :param d_model: int
            Embeddings Size
        :param num_heads: int
            The number of heads the layer should have
        :param num_features: int
            Number of features to be used in Gaussian Matrix
        :param name: str
            The name of layer.
    """

    def __init__(self, d_model: int, num_heads: int, num_features: int, name: str = "MultiHeadPerformer", **kwargs):
        self.num_features = num_features
        super().__init__(d_model, num_heads, name, **kwargs)
        self.random_feats = orthogonal_gaussian(self.num_features, self.depth)

    def call(self, inputs: Dict):
        query, key, value = inputs['query'], inputs['key'], inputs['value']

        batch_size = tf.shape(query)[0]

        # linear layers
        query = self.query_dense(query)
        key = self.key_dense(key)
        value = self.value_dense(value)

        # split heads
        query = self.split_heads(query, batch_size)  # B, H, L, D
        key = self.split_heads(key, batch_size)  # B, H, L, D
        value = self.split_heads(value, batch_size)  # B, H, L, D

        scaled_attention = positive_attention(query=query, key=key, value=value,
                                              random_feats=self.random_feats)

        scaled_attention = tf.transpose(scaled_attention, perm=[0, 2, 1, 3])

        concat_attention = tf.reshape(scaled_attention,
                                      (batch_size, -1, self.d_model))

        outputs = self.dense(concat_attention)

        return outputs

    def get_config(self):
        cfg = {'d_model': self.d_model,
               'num_heads': self.num_heads,
               'num_features': self.num_features}
        return cfg


@tf.keras.utils.register_keras_serializable('GavinCore')
class MultiHeadPerformerReluAttention(GavinMultiHeadPerformerAttention):
    def call(self, inputs: Dict):
        query, key, value = inputs['query'], inputs['key'], inputs['value']
        batch_size = tf.shape(query)[0]

        # linear layers
        query = self.query_dense(query)
        key = self.key_dense(key)
        value = self.value_dense(value)

        # split heads
        query = self.split_heads(query, batch_size)  # B, H, L, D
        key = self.split_heads(key, batch_size)  # B, H, L, D
        value = self.split_heads(value, batch_size)  # B, H, L, D

        scaled_attention = positive_relu_attention(query=query, key=key, value=value,
                                                   random_feats=self.random_feats)

        scaled_attention = tf.transpose(scaled_attention, perm=[0, 2, 1, 3])

        concat_attention = tf.reshape(scaled_attention,
                                      (batch_size, -1, self.d_model))

        outputs = self.dense(concat_attention)

        return outputs


@tf.keras.utils.register_keras_serializable('GavinCore')
class PaddingMaskLayer(tf.keras.layers.Layer):
    def __init__(self, name: str = "padding_mask", **kwargs):
        super(PaddingMaskLayer, self).__init__(name=name, **kwargs)

    def call(self, inputs: tf.Tensor, **kwargs):
        mask = tf.cast(tf.math.equal(inputs, 0), tf.float32)
        return mask[:, tf.newaxis, tf.newaxis, :]

    def get_config(self):
        cfg = {}
        return cfg


@tf.keras.utils.register_keras_serializable('GavinCore')
class LookAheadMaskLayer(tf.keras.layers.Layer):
    def __init__(self, name: str = "look_ahead_mask", **kwargs):
        super(LookAheadMaskLayer, self).__init__(name=name, **kwargs)
        self.padding_mask = PaddingMaskLayer()

    def call(self, inputs: tf.Tensor, **kwargs):
        seq_len = tf.shape(inputs)[1]
        look_ahead_mask = 1 - tf.linalg.band_part(tf.ones((seq_len, seq_len)), -1, 0)
        padding_mask = self.padding_mask(inputs)
        return tf.maximum(look_ahead_mask, padding_mask)

    def get_config(self):
        cfg = {}
        return cfg


# noinspection PyAttributeOutsideInit
class GPUEnabledEmbedding(tf.keras.layers.Embedding):
    """Embedding Layers are forced to run on CPUs which seriously
    hurts training performance this fixes that issue."""

    @tf_utils.shape_type_conversion
    def build(self, _):
        self.embeddings = self.add_weight(
            shape=(self.input_dim, self.output_dim),
            initializer=self.embeddings_initializer,
            name="embeddings",
            regularizer=self.embeddings_regularizer,
            constraint=self.embeddings_constraint,
        )
        self.built = True
