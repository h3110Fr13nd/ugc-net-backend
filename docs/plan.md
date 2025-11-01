## 🗺️ The Overall Plan

Your app can be broken down into a few core "domains." I'll structure the API plan around these domains.

1.  **Auth & User Domain:** (Who is this user?)
2.  **Taxonomy Domain:** (Admin: How is content structured?)
3.  **Authoring Domain:** (Admin/Author: How is content *created*?)
4.  **Learning Domain:** (Student: How is content *consumed*?)
5.  **Statistics Domain:** (Student: How am I *performing*?)
6.  **Utility Domain:** (Media, Relationships)

---

## 🔑 Key Business Logic to Plan For

Before the APIs, these are the two most complex pieces of logic you'll need to write. **Everything else is just standard CRUD.**

1.  **The Statistics Engine (The "Secret Sauce"):**
    * **When:** A user submits an answer (`POST .../submit-answer`).
    * **What:** Your application must perform these steps in a single transaction:
        1.  Grade the `QuestionAttempt` (get `score` and `max_score`).
        2.  Find all `Taxonomy` nodes linked to this question (via `QuestionTaxonomy`).
        3.  For **each** `taxonomy_id` (e.g., "Subtopic: Binary Addition"):
            * Recursively find all its parents (e.g., "Topic: Arithmetic," "Chapter: Digital Logic," "Subject: Computer Science").
            * For this *entire list* of taxonomy nodes, you must **`UPSERT`** (create or update) a row in the `UserTaxonomyStats` table.
            * You'll increment `questions_attempted`, `questions_correct`, `total_score`, etc.
            * Finally, recalculate `average_score_percent`.
    * **Why:** This pre-calculates (denormalizes) all stats. When the user asks "How am I doing in Computer Science?", you just `SELECT` **one row** from `UserTaxonomyStats`. It's incredibly fast.

2.  **The Content Versioning Engine:**
    * **When:** An "Author" user wants to *publish* a new version of a quiz.
    * **What:** You'll create a `POST /quizzes/{quiz_id}/publish` endpoint.
    * **Logic:**
        1.  Create a new `QuizVersion` row.
        2.  Fetch the *current* state of all `Question`s linked to this quiz.
        3.  For each question, create a new `QuestionVersion` (if it doesn't already exist for this state).
        4.  Bundle all this data (the quiz settings, the list of `question_version_id`s, and snapshots of all questions/options/parts) into a single JSONB object.
        5.  Save this object in the `QuizVersion.snapshot` column.
    * **Why:** When a student takes a quiz (`POST .../start-attempt`), they are *always* taking a specific `QuizVersion`. This ensures that if an author edits a question *after* the student starts, the student's quiz doesn't change mid-attempt.

---

## 🛠️ API Endpoint Plan (RESTful)

Here is a logical breakdown of the API endpoints you'll need.

### 1. 🔐 Auth & User Management

* `POST /auth/register`: Create a new `User`.
* `POST /auth/login`: (Email/Password) Returns JWT Access and Refresh tokens. Store the refresh token in `refresh_tokens` table.
* `POST /auth/refresh`: (Requires Refresh Token) Issues a new Access Token. Implements token rotation.
* `POST /auth/logout`: (Requires Refresh Token) Revokes the token from `refresh_tokens`.
* `POST /auth/oauth/google`: (Or other providers) Initiates OAuth flow.
* `GET /auth/oauth/google/callback`: Handles the OAuth callback, creates `User` and `UserOAuthAccount`, issues tokens.
* `GET /users/me`: Get the profile for the currently logged-in user.
* `PUT /users/me`: Update the current user's profile (e.g., `display_name`).

### 2. 📚 Taxonomy (Content Structure)

* `POST /taxonomy`: Create a new taxonomy node (a subject, chapter, or topic).
* `GET /taxonomy/tree`: **(Crucial Endpoint)** Get the *entire* taxonomy as a nested tree structure for navigation.
* `GET /taxonomy/{node_id}`: Get details for a single node (and its direct children).
* `PUT /taxonomy/{node_id}`: Update a node's name or description.
* `PUT /taxonomy/{node_id}/move`: Change the `parent_id` of a node.
* `DELETE /taxonomy/{node_id}`: Delete a node (be careful with cascading deletes).

### 3. ✍️ Authoring (Quizzes & Questions)

* **Questions:**
    * `POST /questions`: Create a new `Question`. The request body will be a complex JSON object containing `parts`, `options`, `option_parts`, and the correct answers.
    * `GET /questions/{question_id}`: Get the *latest* version of a question for editing.
    * `PUT /questions/{question_id}`: Update a question.
    * `POST /questions/{question_id}/taxonomy`: Link a question to a taxonomy node (creates a `QuestionTaxonomy` row).
    * `DELETE /questions/{question_id}/taxonomy/{taxonomy_id}`: Unlink a question.
    * `GET /questions/search?topic=...&difficulty=...`: Find questions.
* **Quizzes:**
    * `POST /quizzes`: Create a new quiz (draft).
    * `GET /quizzes`: List all quizzes.
    * `GET /quizzes/{quiz_id}`: Get quiz metadata (title, etc.) and its list of questions.
    * `PUT /quizzes/{quiz_id}`: Update quiz metadata.
    * `POST /quizzes/{quiz_id}/publish`: **(Key Logic)** Triggers the versioning/snapshot logic described above.
    * `GET /quizzes/{quiz_id}/versions`: Get a list of all published `QuizVersion`s.

### 4. 🚀 Learning (Taking a Quiz)

* `GET /quizzes/published`: Get a list of all published quizzes for a student to take.
* `POST /quizzes/{quiz_id}/start`: Start a new `QuizAttempt`. This should use the *latest published version* of the quiz.
* `GET /quiz-attempts/{attempt_id}`: Get the current state of an "in_progress" attempt (to resume).
* `POST /quiz-attempts/{attempt_id}/submit-answer`:
    * **Body:** `{ "question_id": "...", "selected_option_ids": ["..."] }`
    * **Action:** Creates `QuestionAttempt`, grades it, triggers the **Statistics Engine**, and returns the *next* question in the quiz.
* `POST /quiz-attempts/{attempt_id}/finish`: Mark the quiz as `submitted_at` and calculate final `score`.
* `GET /quiz-attempts/{attempt_id}/results`: Get the full, graded review of a completed quiz.

### 5. 📊 Statistics & Reporting

* `GET /stats/me/dashboard`: **(Key Endpoint)** Returns the user's overall proficiency, recent activity, etc.
* `GET /stats/me/taxonomy/tree`: **(Killer Feature)** Returns the *same* tree as `GET /taxonomy/tree`, but each node is *annotated* with the user's data from `UserTaxonomyStats` (e.g., `{"name": "Computer Science", "average_score_percent": 82, "children": [...] }`). This is your main stats page.
* `GET /stats/me/taxonomy/{node_id}`: Get detailed stats for one specific topic (e.g., attempt history).
* `GET /stats/me/attempts`: Get a list of all past `QuizAttempt`s.

### 6. 🖼️ Utilities (Media & Relationships)

* `POST /media/upload`: (Multipart form data) Uploads a file, saves it to S3/GCS, creates a `Media` row, and returns the new `media_id` and `url`.
* `POST /relationships`: Create a dynamic link between any two entities (e.g., link a Topic to another Topic as a 'prerequisite').
* `GET /relationships?source_id=...&source_type=...`: Get all dynamic links for a given entity.

---

## 💡 Other Key Considerations

* **Authentication Strategy:** Use **JWTs** (JSON Web Tokens). Store the Access Token in memory on the client. Store the Refresh Token in a **`httpOnly`, `secure` cookie** to prevent XSS attacks. Your `POST /auth/refresh` endpoint will read this cookie.
* **Authorization (RBAC):** Your API needs to be protected. Use middleware to check the user's JWT.
    * **`Student` Role:** Can only access `/users/me`, the `/quizzes/published`, `/quiz-attempts`, and `/stats` routes.
    * **`Author` Role:** Can do everything a `Student` can, plus all `/questions` and `/quizzes` routes.
    * **`Admin` Role:** Can do everything, plus `/taxonomy` and `/admin/...` routes (for managing users, roles, etc.).
* **Tech Stack (Suggestions):**
    * **Backend:** **FastAPI** (Python) is an excellent choice as it works perfectly with SQLAlchemy and Pydantic (for data validation).
    * **Database:** You're already set with **PostgreSQL** (especially if you use the `ltree` extension for the `Taxonomy.path` column).
    * **Frontend:** **React** or **Vue** for building the interactive UI.
    * **File Storage:** **AWS S3** or **Google Cloud Storage** for the `Media` table.
* **First Steps:**
    1.  Start with the **Auth** endpoints. You can't do anything else without them.
    2.  Build the **Taxonomy** CRUD. This is the backbone.
    3.  Build the **Question & Quiz Authoring** endpoints.
    4.  Build the **Statistics Engine** logic. This is your hardest task.
    5.  Build the **Quiz Taking** flow.
    6.  Build the **Statistics Reporting** endpoints. This will be easy and rewarding because you did the hard work in step 4.

