# Tutorial Implementation Guide

This document describes the complete tutorial system implemented for the NORD Accounting System, including both user-facing and developer documentation.

## Overview

The tutorial system provides:
1. **User Tutorial** - Step-by-step guides for non-programmers on how to use the application
2. **Developer Tutorial** - API documentation and technical guides for developers
3. **Wizard-Ready HTML** - Formatted HTML suitable for wizard/onboarding components

## Files Created

### 1. `core/tutorial_data.py`
Contains all tutorial content organized as a list of step dictionaries. Each step includes:
- `audience`: `"user"` or `"developer"`
- `id`: Unique identifier (e.g., `"getting-started"`, `"api-transactions"`)
- `title`: Display title
- `html`: HTML content for the step

### 2. `core/views.py` (TutorialView)
Django REST Framework view that serves the tutorial data in multiple formats:
- **JSON format** (default): Returns structured data for programmatic consumption
- **HTML format**: Returns complete HTML page with all steps

### 3. URL Route
Added to `core/urls.py`:
```python
path("api/tutorial/", TutorialView.as_view(), name="tutorial"),
```

## API Endpoint

### Base URL
```
GET /api/tutorial/
```

### Query Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `audience` | string | Filter by audience: `"user"`, `"developer"`, or omit for all | `?audience=user` |
| `format` | string | Response format: `"json"` (default) or `"html"` | `?format=html` |
| `step_id` | string | Get a specific step by ID | `?step_id=getting-started` |

### Examples

#### Get all user tutorial steps (JSON)
```http
GET /api/tutorial/?audience=user
Authorization: Token {your_token}
```

**Response:**
```json
{
  "count": 9,
  "audience": "user",
  "steps": [
    {
      "audience": "user",
      "id": "getting-started",
      "title": "Getting Started with NORD",
      "html": "<div class=\"wizard-step\">...</div>"
    },
    ...
  ]
}
```

#### Get all developer tutorial steps (JSON)
```http
GET /api/tutorial/?audience=developer
```

#### Get a specific step
```http
GET /api/tutorial/?step_id=api-transactions
```

#### Get HTML format (complete page)
```http
GET /api/tutorial/?format=html&audience=user
```

**Response:** Complete HTML page with all tutorial steps styled and ready to display.

## Tutorial Content

### User Tutorial Steps

1. **Getting Started with NORD** (`getting-started`)
   - Introduction to the system
   - First steps after login

2. **Understanding the Navigation** (`navigation-overview`)
   - Main sections overview
   - How to navigate the app

3. **Working with Transactions** (`transactions-basics`)
   - Creating transactions
   - Adding journal entries
   - Posting transactions

4. **Bank Reconciliation Overview** (`bank-reconciliation-overview`)
   - Understanding the reconciliation process
   - Key pages and workflows

5. **Importing Bank Transactions** (`importing-bank-transactions`)
   - Step-by-step OFX import process
   - After import workflow

6. **Running Automated Reconciliation** (`running-reconciliation`)
   - Starting reconciliation tasks
   - Monitoring and reviewing suggestions

7. **Manual Reconciliation** (`manual-reconciliation`)
   - Manual matching process
   - Getting suggestions for single transactions

8. **Managing Your Chart of Accounts** (`chart-of-accounts`)
   - Viewing and creating accounts
   - Account hierarchy and activity

9. **Generating Financial Statements** (`financial-statements`)
   - Creating statements from templates
   - Viewing and comparing periods

10. **Filtering and Searching** (`filtering-and-search`)
    - Using filters and tabs
    - Table features

### Developer Tutorial Steps

1. **API Authentication** (`api-authentication`)
   - Login endpoint
   - Token authentication
   - Multi-tenancy

2. **Transactions API** (`api-transactions`)
   - List, create, post transactions
   - Related endpoints

3. **Bank Reconciliation API** (`api-bank-reconciliation`)
   - Import OFX
   - Get suggestions
   - Reconciliation tasks
   - Dashboard endpoints

4. **Financial Statements API** (`api-financial-statements`)
   - Generate statements
   - Comparisons and time series
   - Template management

5. **Common API Patterns** (`api-common-patterns`)
   - Pagination
   - Filtering
   - Ordering
   - Error handling

6. **Accounts and Journal Entries API** (`api-accounts-journal`)
   - Chart of accounts endpoints
   - Journal entries management

## Integration with Wizard Component

The tutorial is designed to work with wizard/onboarding components. Each step's HTML is wrapped in a `<div class="wizard-step">` with data attributes:

```html
<div class="wizard-step" data-audience="user" data-step-id="getting-started">
  <!-- Step content -->
</div>
```

### Frontend Integration Example

```javascript
// Fetch tutorial steps
const response = await fetch('/api/tutorial/?audience=user', {
  headers: {
    'Authorization': `Token ${token}`
  }
});

const data = await response.json();

// Render in wizard component
data.steps.forEach((step, index) => {
  // step.html contains the HTML for this step
  // step.id is the unique identifier
  // step.title is the display title
  wizard.addStep({
    id: step.id,
    title: step.title,
    content: step.html,
    index: index
  });
});
```

## Styling

The HTML format includes embedded CSS that provides:
- Clean, readable typography
- Color-coded audience badges (user/developer)
- Syntax highlighting for code blocks
- Responsive layout
- Professional appearance

The wizard component can use these styles or override them as needed.

## Extending the Tutorial

To add new tutorial steps:

1. Open `core/tutorial_data.py`
2. Add a new dictionary to the `TUTORIAL_STEPS` list:

```python
{
    "audience": "user",  # or "developer"
    "id": "my-new-step",
    "title": "My New Tutorial Step",
    "html": """
    <div class="wizard-step" data-audience="user" data-step-id="my-new-step">
      <h2>My New Tutorial Step</h2>
      <p>Content here...</p>
    </div>
    """
}
```

3. The new step will automatically be available via the API

## Testing

### Test JSON Response
```bash
curl -H "Authorization: Token YOUR_TOKEN" \
     http://localhost:8000/api/tutorial/?audience=user
```

### Test HTML Response
```bash
curl -H "Authorization: Token YOUR_TOKEN" \
     "http://localhost:8000/api/tutorial/?format=html&audience=user" \
     > tutorial.html
```

Then open `tutorial.html` in a browser.

### Test Specific Step
```bash
curl -H "Authorization: Token YOUR_TOKEN" \
     "http://localhost:8000/api/tutorial/?step_id=getting-started"
```

## Authentication

The tutorial endpoint requires authentication:
- Uses `IsAuthenticated` permission class
- Requires valid DRF token in Authorization header
- Works with multi-tenant setup (tenant extracted from URL)

## Future Enhancements

Potential improvements:
1. **Progress Tracking** - Track which steps users have completed
2. **Interactive Examples** - Embed live API calls in developer tutorial
3. **Video Tutorials** - Link to video content
4. **Search** - Full-text search across tutorial content
5. **Localization** - Multi-language support
6. **Versioning** - Track tutorial versions with API versions
7. **Feedback** - Allow users to rate/comment on tutorial steps

## Related Documentation

- [UI/UX Documentation](./UI_UX_DOCUMENTATION.md) - Complete frontend design specification
- [API Overview](./frontend/docs/api_overview.md) - API endpoint documentation
- [Retool UI/UX Analysis](./frontend/RETOOL_UI_UX_ANALYSIS.md) - Retool frontend analysis

