# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2017-02-06 20:27
from __future__ import unicode_literals

import django.db.models.deletion
from django.db import migrations, models

import pretix.base.models.base


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0050_orderposition_positionid_squashed_0061_event_location'),
    ]

    operations = [
        migrations.CreateModel(
            name='WaitingListEntry',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='On waiting list since')),
                ('email', models.EmailField(max_length=254, verbose_name='Email address')),
                ('locale', models.CharField(default='en', max_length=190)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='waitinglistentries', to='pretixbase.Event', verbose_name='Event')),
                ('item', models.ForeignKey(help_text='The product the user waits for.', on_delete=django.db.models.deletion.CASCADE, related_name='waitinglistentries', to='pretixbase.Item', verbose_name='Product')),
                ('variation', models.ForeignKey(blank=True, help_text='The variation of the product selected above.', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='waitinglistentries', to='pretixbase.ItemVariation', verbose_name='Product variation')),
                ('voucher', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='pretixbase.Voucher', verbose_name='Assigned voucher')),
            ],
            options={
                'ordering': ['created'],
                'verbose_name': 'Waiting list entry',
                'verbose_name_plural': 'Waiting list entries',
            },
            bases=(models.Model, pretix.base.models.base.LoggingMixin),
        ),
        migrations.AlterField(
            model_name='cachedcombinedticket',
            name='created',
            field=models.DateTimeField(auto_now_add=True),
        ),
    ]
