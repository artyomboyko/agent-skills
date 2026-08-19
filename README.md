# Agent Skills

A collection of portable Agent Skills compatible with GitHub Copilot, OpenAI Codex, and other Agent Skills-compatible tools.

Skills in this repository follow the open Agent Skills format.

## Available Skills

### translate-web-course-to-notebook

Translates or audits online course, tutorial, and documentation pages into a Jupyter Notebook while preserving the original structure, links, code, images, quizzes, and other learner-visible content.

Skill path:

`plugins/course-localization/skills/translate-web-course-to-notebook`

Requirements:

- Python 3.10+
- No third-party Python dependencies
- Web/network access
- Authenticated or browser-capable access may be needed for dynamic or protected pages

#### Usage example

```text
$translate-web-course-to-notebook

Исходники:
https://learn.microsoft.com/en-us/training/modules/github-actions-automate-tasks/1-introduction
https://learn.microsoft.com/en-us/training/modules/github-actions-automate-tasks/2-github-actions-automate-development-tasks
https://learn.microsoft.com/en-us/training/modules/github-actions-automate-tasks/2b-identify-components-workflow
https://learn.microsoft.com/en-us/training/modules/github-actions-automate-tasks/2c-configure-github-actions-workflow
https://learn.microsoft.com/en-us/training/modules/github-actions-automate-tasks/3-exercise-create-container-action
https://learn.microsoft.com/en-us/training/modules/github-actions-automate-tasks/4-knowledge-check

Файл:
C:\path\to\course\Module.ipynb

Папка для картинок курса:
C:\path\to\course\img
```
