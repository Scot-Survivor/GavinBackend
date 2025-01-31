import os
import unittest

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
from GavinCore.models import TransformerIntegration, tfds, PerformerIntegration, FNetIntegration
from GavinCore.utils import tf
from GavinCore.datasets import DatasetAPICreator
from GavinCore.metrics import Perplexity, Precision
from GavinCore.load_data import load_tokenized_data
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
physical_devices = tf.config.list_physical_devices('GPU')
try:
    for device in physical_devices:
        tf.config.experimental.set_memory_growth(device, True)
except Exception as e:
    print(f"Error on Memory Growth Setting. {e}")
else:
    print("Memory Growth Set to True.")


data_set_path = os.getenv('TEST_DATA_PATH')
should_use_python = bool(os.getenv('USE_PYTHON_LOADER', True))


class Metrics(unittest.TestCase):
    def setUp(self) -> None:
        self.tokenizer_path = os.path.join(BASE_DIR, os.path.join('tests/test_files', 'Tokenizer-3'))
        self.tokenizer = tfds.deprecated.text.SubwordTextEncoder.load_from_file(self.tokenizer_path)
        self.max_samples = 10_000
        self.buffer_size = 20_000
        self.batch_size = 32
        self.hparams = {
            'NUM_LAYERS': 1,
            'UNITS': 256,
            'D_MODEL': 128,
            'NUM_HEADS': 2,
            'DROPOUT': 0.1,
            'MAX_LENGTH': 52,
            'TOKENIZER': self.tokenizer,
            'MODEL_NAME': "TestTransformer",
            'FLOAT16': False,
            'EPOCHS': 0,
            'BATCH_SIZE': self.batch_size
        }
        self.config_for_models = self.hparams.copy()
        self.config_for_models = {k.lower(): v for k, v in self.config_for_models.items()}
        self.config_for_models['max_len'] = self.config_for_models['max_length']
        self.config_for_models['name'] = self.config_for_models['model_name']
        self.config_for_models['mixed'] = self.config_for_models['float16']
        self.config_for_models['base_log_dir'] = '../models/'
        del self.config_for_models['max_length'], self.config_for_models['model_name'], self.config_for_models[
            'float16']
        tf.keras.backend.clear_session()  # Reduces the amount of memory this will use.
        self.should_use_python_legacy = should_use_python
        self.should_use_cpp_legacy = False
        self.data_set_path = data_set_path

    def test_001_accuracy_metric_transformer(self):
        try:
            base = TransformerIntegration(**self.config_for_models)
            base.metrics.append("accuracy")
        except Exception as err:
            self.fail(f"Model creation failed: {err}")
        self.assertTrue(hasattr(base, "model"), "Model not created.")
        questions, answers = load_tokenized_data(max_samples=self.max_samples,
                                                 data_path=self.data_set_path,
                                                 filename="Tokenizer-3",
                                                 s_token=base.start_token,
                                                 e_token=base.end_token, max_len=base.max_len,
                                                 cpp_legacy=self.should_use_cpp_legacy,
                                                 python_legacy=self.should_use_python_legacy)

        if self.should_use_python_legacy:
            questions = tf.keras.preprocessing.sequence.pad_sequences(questions, maxlen=base.max_len, padding='post')
            answers = tf.keras.preprocessing.sequence.pad_sequences(answers, maxlen=base.max_len, padding='post')

        dataset_train, dataset_val = DatasetAPICreator.create_data_objects(questions, answers,
                                                                           buffer_size=self.buffer_size,
                                                                           batch_size=self.batch_size,
                                                                           vocab_size=base.vocab_size)
        try:
            base.fit(training_dataset=dataset_train, validation_dataset=dataset_val,
                     epochs=1)
        except Exception as err:
            self.fail(f"Model Fit failed: {err}")

    @unittest.expectedFailure
    def test_002_precision_metric_transformer(self):
        try:
            base = TransformerIntegration(**self.config_for_models)
            with base.strategy.scope():
                base.metrics.append(Precision(max_len=self.hparams['MAX_LENGTH'], from_logits=True))
        except Exception as err:
            self.fail(f"Model creation failed: {err}")
        self.assertTrue(hasattr(base, "model"), "Model not created.")
        questions, answers = load_tokenized_data(max_samples=self.max_samples,
                                                 data_path=self.data_set_path,
                                                 filename="Tokenizer-3",
                                                 s_token=base.start_token,
                                                 e_token=base.end_token, max_len=base.max_len,
                                                 cpp_legacy=self.should_use_cpp_legacy,
                                                 python_legacy=self.should_use_python_legacy)

        if self.should_use_python_legacy:
            questions = tf.keras.preprocessing.sequence.pad_sequences(questions, maxlen=base.max_len, padding='post')
            answers = tf.keras.preprocessing.sequence.pad_sequences(answers, maxlen=base.max_len, padding='post')

        dataset_train, dataset_val = DatasetAPICreator.create_data_objects(questions, answers,
                                                                           buffer_size=self.buffer_size,
                                                                           batch_size=self.batch_size,
                                                                           vocab_size=base.vocab_size)
        try:
            base.fit(training_dataset=dataset_train, validation_dataset=dataset_val,
                     epochs=1)
        except Exception as err:
            self.fail(f"Model Fit failed: {err}")

    def test_003_perplexity_metric_transformer(self):
        try:
            base = TransformerIntegration(**self.config_for_models)
            with base.strategy.scope():
                base.metrics.append(
                    Perplexity(max_len=self.hparams['MAX_LENGTH'], vocab_size=self.tokenizer.vocab_size))
        except Exception as err:
            self.fail(f"Model creation failed: {err}")
        self.assertTrue(hasattr(base, "model"), "Model not created.")
        questions, answers = load_tokenized_data(max_samples=self.max_samples,
                                                 data_path=self.data_set_path,
                                                 filename="Tokenizer-3",
                                                 s_token=base.start_token,
                                                 e_token=base.end_token, max_len=base.max_len,
                                                 cpp_legacy=self.should_use_cpp_legacy,
                                                 python_legacy=self.should_use_python_legacy)

        if self.should_use_python_legacy:
            questions = tf.keras.preprocessing.sequence.pad_sequences(questions, maxlen=base.max_len, padding='post')
            answers = tf.keras.preprocessing.sequence.pad_sequences(answers, maxlen=base.max_len, padding='post')

        dataset_train, dataset_val = DatasetAPICreator.create_data_objects(questions, answers,
                                                                           buffer_size=self.buffer_size,
                                                                           batch_size=self.batch_size,
                                                                           vocab_size=base.vocab_size)
        try:
            base.fit(training_dataset=dataset_train, validation_dataset=dataset_val,
                     epochs=1)
        except Exception as err:
            self.fail(f"Model Fit failed: {err}")

    def test_004_accuracy_metric_performer(self):
        try:
            base = PerformerIntegration(**self.config_for_models, num_features=128)
            base.metrics.append('accuracy')
        except Exception as err:
            self.fail(f"Model creation failed: {err}")
        self.assertTrue(hasattr(base, "model"), "Model not created.")
        questions, answers = load_tokenized_data(max_samples=self.max_samples,
                                                 data_path=self.data_set_path,
                                                 filename="Tokenizer-3",
                                                 s_token=base.start_token,
                                                 e_token=base.end_token, max_len=base.max_len,
                                                 cpp_legacy=self.should_use_cpp_legacy,
                                                 python_legacy=self.should_use_python_legacy)

        if self.should_use_python_legacy:
            questions = tf.keras.preprocessing.sequence.pad_sequences(questions, maxlen=base.max_len, padding='post')
            answers = tf.keras.preprocessing.sequence.pad_sequences(answers, maxlen=base.max_len, padding='post')

        dataset_train, dataset_val = DatasetAPICreator.create_data_objects(questions, answers,
                                                                           buffer_size=self.buffer_size,
                                                                           batch_size=self.batch_size,
                                                                           vocab_size=base.vocab_size)
        try:
            base.fit(training_dataset=dataset_train, validation_dataset=dataset_val,
                     epochs=1)
        except Exception as err:
            self.fail(f"Model Fit failed: {err}")

    @unittest.expectedFailure
    def test_005_precision_metric_performer(self):
        try:
            base = PerformerIntegration(**self.config_for_models, num_features=128)
            with base.strategy.scope():
                base.metrics.append(Precision(max_len=self.hparams['MAX_LENGTH'], from_logits=True))
        except Exception as err:
            self.fail(f"Model creation failed: {err}")
        self.assertTrue(hasattr(base, "model"), "Model not created.")
        questions, answers = load_tokenized_data(max_samples=self.max_samples,
                                                 data_path=self.data_set_path,
                                                 filename="Tokenizer-3",
                                                 s_token=base.start_token,
                                                 e_token=base.end_token, max_len=base.max_len,
                                                 cpp_legacy=self.should_use_cpp_legacy,
                                                 python_legacy=self.should_use_python_legacy)

        if self.should_use_python_legacy:
            questions = tf.keras.preprocessing.sequence.pad_sequences(questions, maxlen=base.max_len, padding='post')
            answers = tf.keras.preprocessing.sequence.pad_sequences(answers, maxlen=base.max_len, padding='post')

        dataset_train, dataset_val = DatasetAPICreator.create_data_objects(questions, answers,
                                                                           buffer_size=self.buffer_size,
                                                                           batch_size=self.batch_size,
                                                                           vocab_size=base.vocab_size)
        try:
            base.fit(training_dataset=dataset_train, validation_dataset=dataset_val,
                     epochs=1)
        except Exception as err:
            self.fail(f"Model Fit failed: {err}")

    def test_006_perplexity_metric_performer(self):
        try:
            base = PerformerIntegration(**self.config_for_models, num_features=128)
            with base.strategy.scope():
                base.metrics.append(
                    Perplexity(max_len=self.hparams['MAX_LENGTH'], vocab_size=self.tokenizer.vocab_size))
        except Exception as err:
            self.fail(f"Model creation failed: {err}")
        self.assertTrue(hasattr(base, "model"), "Model not created.")
        questions, answers = load_tokenized_data(max_samples=self.max_samples,
                                                 data_path=self.data_set_path,
                                                 filename="Tokenizer-3",
                                                 s_token=base.start_token,
                                                 e_token=base.end_token, max_len=base.max_len,
                                                 cpp_legacy=self.should_use_cpp_legacy,
                                                 python_legacy=self.should_use_python_legacy)

        if self.should_use_python_legacy:
            questions = tf.keras.preprocessing.sequence.pad_sequences(questions, maxlen=base.max_len, padding='post')
            answers = tf.keras.preprocessing.sequence.pad_sequences(answers, maxlen=base.max_len, padding='post')

        dataset_train, dataset_val = DatasetAPICreator.create_data_objects(questions, answers,
                                                                           buffer_size=self.buffer_size,
                                                                           batch_size=self.batch_size,
                                                                           vocab_size=base.vocab_size)
        try:
            base.fit(training_dataset=dataset_train, validation_dataset=dataset_val,
                     epochs=1)
        except Exception as err:
            self.fail(f"Model Fit failed: {err}")

    def test_007_accuracy_metric_fnet(self):
        try:
            base = FNetIntegration(**self.config_for_models, num_features=128)
            with base.strategy.scope():
                base.metrics.append('accuracy')
        except Exception as err:
            self.fail(f"Model creation failed: {err}")

        self.assertTrue(hasattr(base, "model"), "Model not created.")
        questions, answers = load_tokenized_data(max_samples=self.max_samples,
                                                 data_path=self.data_set_path,
                                                 filename="Tokenizer-3",
                                                 s_token=base.start_token,
                                                 e_token=base.end_token, max_len=base.max_len,
                                                 cpp_legacy=self.should_use_cpp_legacy,
                                                 python_legacy=self.should_use_python_legacy)

        if self.should_use_python_legacy:
            questions = tf.keras.preprocessing.sequence.pad_sequences(questions, maxlen=base.max_len, padding='post')
            answers = tf.keras.preprocessing.sequence.pad_sequences(answers, maxlen=base.max_len, padding='post')

        dataset_train, dataset_val = DatasetAPICreator.create_data_objects(questions, answers,
                                                                           buffer_size=self.buffer_size,
                                                                           batch_size=self.batch_size,
                                                                           vocab_size=base.vocab_size)
        try:
            base.fit(training_dataset=dataset_train, validation_dataset=dataset_val,
                     epochs=1)
        except Exception as err:
            self.fail(f"Model Fit failed: {err}")

    @unittest.expectedFailure
    def test_008_precision_metric_fnet(self):
        try:
            base = FNetIntegration(**self.config_for_models)
            with base.strategy.scope():
                base.metrics.append(Precision(max_len=self.hparams['MAX_LENGTH'], vocab_size=self.tokenizer.vocab_size))
        except Exception as err:
            self.fail(f"Model creation failed: {err}")

        self.assertTrue(hasattr(base, 'model'), "Model not created.")
        questions, answers = load_tokenized_data(max_samples=self.max_samples,
                                                 data_path=self.data_set_path,
                                                 filename="Tokenizer-3",
                                                 s_token=base.start_token,
                                                 e_token=base.end_token, max_len=base.max_len,
                                                 cpp_legacy=self.should_use_cpp_legacy,
                                                 python_legacy=self.should_use_python_legacy)

        if self.should_use_python_legacy:
            questions = tf.keras.preprocessing.sequence.pad_sequences(questions, maxlen=base.max_len, padding='post')
            answers = tf.keras.preprocessing.sequence.pad_sequences(answers, maxlen=base.max_len, padding='post')

        dataset_train, dataset_val = DatasetAPICreator.create_data_objects(questions, answers,
                                                                           buffer_size=self.buffer_size,
                                                                           batch_size=self.batch_size,
                                                                           vocab_size=base.vocab_size)

        try:
            base.fit(training_dataset=dataset_train, validation_dataset=dataset_val,
                     epochs=1)
        except Exception as err:
            self.fail(f"Model Fit failed: {err}")

    def test_009_perplexity_metric_fnet(self):
        try:
            base = FNetIntegration(**self.config_for_models)
            with base.strategy.scope():
                base.metrics.append(
                    Perplexity(max_len=self.hparams['MAX_LENGTH'], vocab_size=self.tokenizer.vocab_size))
        except Exception as err:
            self.fail(f"Model creation failed: {err}")

        self.assertTrue(hasattr(base, 'model'), "Model not created.")
        questions, answers = load_tokenized_data(max_samples=self.max_samples,
                                                 data_path=self.data_set_path,
                                                 filename="Tokenizer-3",
                                                 s_token=base.start_token,
                                                 e_token=base.end_token, max_len=base.max_len,
                                                 cpp_legacy=self.should_use_cpp_legacy,
                                                 python_legacy=self.should_use_python_legacy)

        if self.should_use_python_legacy:
            questions = tf.keras.preprocessing.sequence.pad_sequences(questions, maxlen=base.max_len, padding='post')
            answers = tf.keras.preprocessing.sequence.pad_sequences(answers, maxlen=base.max_len, padding='post')

        dataset_train, dataset_val = DatasetAPICreator.create_data_objects(questions, answers,
                                                                           buffer_size=self.buffer_size,
                                                                           batch_size=self.batch_size,
                                                                           vocab_size=base.vocab_size)

        try:
            base.fit(training_dataset=dataset_train, validation_dataset=dataset_val,
                     epochs=1)
        except Exception as err:
            self.fail(f"Model Fit failed: {err}")
