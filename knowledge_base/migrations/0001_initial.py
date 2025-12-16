# Generated manually - Django migration for knowledge_base app

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('multitenancy', '0001_initial'),
        ('npl', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='KnowledgeBase',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now_add=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('notes', models.TextField(blank=True, help_text='Metadata and notes about how this record was created (source, filename, function, etc.)', null=True)),
                ('name', models.CharField(help_text='Display name for the knowledge base', max_length=255)),
                ('gemini_store_name', models.CharField(help_text='Gemini File Search Store resource name (globally unique)', max_length=255, unique=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='knowledgebase_company', to='multitenancy.company')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='knowledgebase_created_by', to='multitenancy.customuser')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='knowledgebase_updated_by', to='multitenancy.customuser')),
            ],
            options={
                'verbose_name': 'Knowledge Base',
                'verbose_name_plural': 'Knowledge Bases',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Answer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now_add=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('notes', models.TextField(blank=True, help_text='Metadata and notes about how this record was created (source, filename, function, etc.)', null=True)),
                ('question', models.TextField(help_text="User's question")),
                ('answer_text', models.TextField(help_text='Generated answer from Gemini')),
                ('grounding_metadata', models.JSONField(blank=True, default=dict, help_text='Raw grounding metadata from Gemini API')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='answer_company', to='multitenancy.company')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='answer_created_by', to='multitenancy.customuser')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='answer_updated_by', to='multitenancy.customuser')),
                ('knowledge_base', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='answers', to='knowledge_base.knowledgebase')),
            ],
            options={
                'verbose_name': 'Answer',
                'verbose_name_plural': 'Answers',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='KnowledgeDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now_add=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('notes', models.TextField(blank=True, help_text='Metadata and notes about how this record was created (source, filename, function, etc.)', null=True)),
                ('filename', models.CharField(help_text='Original filename', max_length=255)),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('indexing', 'Indexing'), ('ready', 'Ready'), ('failed', 'Failed')], db_index=True, default='queued', max_length=20)),
                ('error', models.TextField(blank=True, help_text="Error message if status is 'failed'", null=True)),
                ('gemini_doc_name', models.CharField(blank=True, help_text='Gemini File Search document resource name', max_length=255, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict, help_text='Custom metadata: file size, mime type, page count, etc.')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='knowledgedocument_company', to='multitenancy.company')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='knowledgedocument_created_by', to='multitenancy.customuser')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='knowledgedocument_updated_by', to='multitenancy.customuser')),
                ('knowledge_base', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='documents', to='knowledge_base.knowledgebase')),
                ('source_document', models.ForeignKey(blank=True, help_text='Optional reference to existing npl.Document', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='knowledge_documents', to='npl.document')),
            ],
            options={
                'verbose_name': 'Knowledge Document',
                'verbose_name_plural': 'Knowledge Documents',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='AnswerFeedback',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now_add=True)),
                ('is_deleted', models.BooleanField(default=False)),
                ('notes', models.TextField(blank=True, help_text='Metadata and notes about how this record was created (source, filename, function, etc.)', null=True)),
                ('rating', models.CharField(choices=[('up', 'Thumbs Up'), ('down', 'Thumbs Down')], help_text='User rating: thumbs up or down', max_length=10)),
                ('comment', models.TextField(blank=True, help_text='Optional user comment', null=True)),
                ('missing_info', models.BooleanField(default=False, help_text='Flag if answer was missing important information')),
                ('answer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='feedback', to='knowledge_base.answer')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='answerfeedback_created_by', to='multitenancy.customuser')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='answerfeedback_updated_by', to='multitenancy.customuser')),
            ],
            options={
                'verbose_name': 'Answer Feedback',
                'verbose_name_plural': 'Answer Feedback',
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='knowledgedocument',
            index=models.Index(fields=['knowledge_base', 'status'], name='knowledge_b_knowled_123_idx'),
        ),
    ]

