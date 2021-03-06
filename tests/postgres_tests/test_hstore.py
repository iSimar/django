import json
import unittest

from django.contrib.postgres import forms
from django.contrib.postgres.fields import HStoreField
from django.contrib.postgres.validators import KeysValidator
from django.core import exceptions, serializers
from django.db import connection
from django.test import TestCase

from .models import HStoreModel


@unittest.skipUnless(connection.vendor == 'postgresql', 'PostgreSQL required')
class SimpleTests(TestCase):
    apps = ['django.contrib.postgres']

    def test_save_load_success(self):
        value = {'a': 'b'}
        instance = HStoreModel(field=value)
        instance.save()
        reloaded = HStoreModel.objects.get()
        self.assertEqual(reloaded.field, value)

    def test_null(self):
        instance = HStoreModel(field=None)
        instance.save()
        reloaded = HStoreModel.objects.get()
        self.assertEqual(reloaded.field, None)

    def test_value_null(self):
        value = {'a': None}
        instance = HStoreModel(field=value)
        instance.save()
        reloaded = HStoreModel.objects.get()
        self.assertEqual(reloaded.field, value)


@unittest.skipUnless(connection.vendor == 'postgresql', 'PostgreSQL required')
class TestQuerying(TestCase):

    def setUp(self):
        self.objs = [
            HStoreModel.objects.create(field={'a': 'b'}),
            HStoreModel.objects.create(field={'a': 'b', 'c': 'd'}),
            HStoreModel.objects.create(field={'c': 'd'}),
            HStoreModel.objects.create(field={}),
            HStoreModel.objects.create(field=None),
        ]

    def test_exact(self):
        self.assertSequenceEqual(
            HStoreModel.objects.filter(field__exact={'a': 'b'}),
            self.objs[:1]
        )

    def test_contained_by(self):
        self.assertSequenceEqual(
            HStoreModel.objects.filter(field__contained_by={'a': 'b', 'c': 'd'}),
            self.objs[:4]
        )

    def test_contains(self):
        self.assertSequenceEqual(
            HStoreModel.objects.filter(field__contains={'a': 'b'}),
            self.objs[:2]
        )

    def test_has_key(self):
        self.assertSequenceEqual(
            HStoreModel.objects.filter(field__has_key='c'),
            self.objs[1:3]
        )

    def test_has_keys(self):
        self.assertSequenceEqual(
            HStoreModel.objects.filter(field__has_keys=['a', 'c']),
            self.objs[1:2]
        )

    def test_key_transform(self):
        self.assertSequenceEqual(
            HStoreModel.objects.filter(field__a='b'),
            self.objs[:2]
        )

    def test_keys(self):
        self.assertSequenceEqual(
            HStoreModel.objects.filter(field__keys=['a']),
            self.objs[:1]
        )

    def test_values(self):
        self.assertSequenceEqual(
            HStoreModel.objects.filter(field__values=['b']),
            self.objs[:1]
        )

    def test_field_chaining(self):
        self.assertSequenceEqual(
            HStoreModel.objects.filter(field__a__contains='b'),
            self.objs[:2]
        )

    def test_keys_contains(self):
        self.assertSequenceEqual(
            HStoreModel.objects.filter(field__keys__contains=['a']),
            self.objs[:2]
        )

    def test_values_overlap(self):
        self.assertSequenceEqual(
            HStoreModel.objects.filter(field__values__overlap=['b', 'd']),
            self.objs[:3]
        )


@unittest.skipUnless(connection.vendor == 'postgresql', 'PostgreSQL required')
class TestSerialization(TestCase):
    test_data = '[{"fields": {"field": "{\\"a\\": \\"b\\"}"}, "model": "postgres_tests.hstoremodel", "pk": null}]'

    def test_dumping(self):
        instance = HStoreModel(field={'a': 'b'})
        data = serializers.serialize('json', [instance])
        self.assertEqual(json.loads(data), json.loads(self.test_data))

    def test_loading(self):
        instance = list(serializers.deserialize('json', self.test_data))[0].object
        self.assertEqual(instance.field, {'a': 'b'})


class TestValidation(TestCase):

    def test_not_a_string(self):
        field = HStoreField()
        with self.assertRaises(exceptions.ValidationError) as cm:
            field.clean({'a': 1}, None)
        self.assertEqual(cm.exception.code, 'not_a_string')
        self.assertEqual(cm.exception.message % cm.exception.params, 'The value of "a" is not a string.')


class TestFormField(TestCase):

    def test_valid(self):
        field = forms.HStoreField()
        value = field.clean('{"a": "b"}')
        self.assertEqual(value, {'a': 'b'})

    def test_invalid_json(self):
        field = forms.HStoreField()
        with self.assertRaises(exceptions.ValidationError) as cm:
            field.clean('{"a": "b"')
        self.assertEqual(cm.exception.messages[0], 'Could not load JSON data.')
        self.assertEqual(cm.exception.code, 'invalid_json')

    def test_not_string_values(self):
        field = forms.HStoreField()
        value = field.clean('{"a": 1}')
        self.assertEqual(value, {'a': '1'})

    def test_empty(self):
        field = forms.HStoreField(required=False)
        value = field.clean('')
        self.assertEqual(value, {})

    def test_model_field_formfield(self):
        model_field = HStoreField()
        form_field = model_field.formfield()
        self.assertIsInstance(form_field, forms.HStoreField)


class TestValidator(TestCase):

    def test_simple_valid(self):
        validator = KeysValidator(keys=['a', 'b'])
        validator({'a': 'foo', 'b': 'bar', 'c': 'baz'})

    def test_missing_keys(self):
        validator = KeysValidator(keys=['a', 'b'])
        with self.assertRaises(exceptions.ValidationError) as cm:
            validator({'a': 'foo', 'c': 'baz'})
        self.assertEqual(cm.exception.messages[0], 'Some keys were missing: b')
        self.assertEqual(cm.exception.code, 'missing_keys')

    def test_strict_valid(self):
        validator = KeysValidator(keys=['a', 'b'], strict=True)
        validator({'a': 'foo', 'b': 'bar'})

    def test_extra_keys(self):
        validator = KeysValidator(keys=['a', 'b'], strict=True)
        with self.assertRaises(exceptions.ValidationError) as cm:
            validator({'a': 'foo', 'b': 'bar', 'c': 'baz'})
        self.assertEqual(cm.exception.messages[0], 'Some unknown keys were provided: c')
        self.assertEqual(cm.exception.code, 'extra_keys')

    def test_custom_messages(self):
        messages = {
            'missing_keys': 'Foobar',
        }
        validator = KeysValidator(keys=['a', 'b'], strict=True, messages=messages)
        with self.assertRaises(exceptions.ValidationError) as cm:
            validator({'a': 'foo', 'c': 'baz'})
        self.assertEqual(cm.exception.messages[0], 'Foobar')
        self.assertEqual(cm.exception.code, 'missing_keys')
        with self.assertRaises(exceptions.ValidationError) as cm:
            validator({'a': 'foo', 'b': 'bar', 'c': 'baz'})
        self.assertEqual(cm.exception.messages[0], 'Some unknown keys were provided: c')
        self.assertEqual(cm.exception.code, 'extra_keys')

    def test_deconstruct(self):
        messages = {
            'missing_keys': 'Foobar',
        }
        validator = KeysValidator(keys=['a', 'b'], strict=True, messages=messages)
        path, args, kwargs = validator.deconstruct()
        self.assertEqual(path, 'django.contrib.postgres.validators.KeysValidator')
        self.assertEqual(args, ())
        self.assertEqual(kwargs, {'keys': ['a', 'b'], 'strict': True, 'messages': messages})
