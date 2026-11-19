/**
 * Generated from docs/openapi.json by scripts/openapi-types.mjs.
 * Do not edit: run npm run api:types. src/api/schema.test.ts fails when stale.
 * Checkorca-CE 27.0.0
 */

export interface paths {
  "/healthz": {
    get: {
      /** Healthz */
      parameters: {
        query: never;
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": Record<string, string | null>;
          };
        };
      };
    };
  };
  "/readyz": {
    get: {
      /** Readyz */
      parameters: {
        query: never;
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": Record<string, unknown>;
          };
        };
      };
    };
  };
  "/api/v1/auth/setup-state": {
    get: {
      /** Setup State */
      parameters: {
        query: never;
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["SetupState"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/auth/first-run": {
    get: {
      /** First Run State */
      parameters: {
        query: never;
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["SetupState"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
    post: {
      /** First Run */
      parameters: {
        query: never;
        path: never;
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["NewAccount"];
        };
      };
      responses: {
        "201": {
          content: {
            "application/json": components["schemas"]["SignedIn"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/auth/login": {
    post: {
      /** Login */
      parameters: {
        query: never;
        path: never;
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["Credentials"];
        };
      };
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["SignedIn"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/auth/logout": {
    post: {
      /** Logout */
      parameters: {
        query: never;
        path: never;
      };
      requestBody?: never;
      responses: {
        "204": {
          content: never;
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/auth/me": {
    get: {
      /** Me */
      parameters: {
        query: never;
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["Me"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/users": {
    get: {
      /** List Users */
      parameters: {
        query: {
          cursor?: string | null;
          limit?: number;
        };
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["UserPage"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
    post: {
      /** Create User */
      parameters: {
        query: never;
        path: never;
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["NewUser"];
        };
      };
      responses: {
        "201": {
          content: {
            "application/json": components["schemas"]["UserOut"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/users/{user_id}": {
    get: {
      /** Get User */
      parameters: {
        query: never;
        path: {
          user_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["UserOut"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
    delete: {
      /** Delete User */
      parameters: {
        query: never;
        path: {
          user_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "204": {
          content: never;
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
    patch: {
      /** Update User */
      parameters: {
        query: never;
        path: {
          user_id: string;
        };
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["UserPatch"];
        };
      };
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["UserOut"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/tokens": {
    get: {
      /** List Tokens */
      parameters: {
        query: {
          cursor?: string | null;
          limit?: number;
        };
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["TokenPage"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
    post: {
      /** Create Token */
      parameters: {
        query: never;
        path: never;
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["NewToken"];
        };
      };
      responses: {
        "201": {
          content: {
            "application/json": components["schemas"]["CreatedToken"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/tokens/{token_id}": {
    delete: {
      /** Revoke Token */
      parameters: {
        query: never;
        path: {
          token_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "204": {
          content: never;
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/clients": {
    get: {
      /** List Clients */
      parameters: {
        query: {
          q?: string | null;
          archived?: boolean;
          cursor?: string | null;
          limit?: number;
        };
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["ClientPage"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
    post: {
      /** Create Client */
      parameters: {
        query: never;
        path: never;
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["NewClient"];
        };
      };
      responses: {
        "201": {
          content: {
            "application/json": components["schemas"]["ClientOut"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/clients/{client_id}": {
    get: {
      /** Get Client */
      parameters: {
        query: never;
        path: {
          client_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["ClientOut"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
    delete: {
      /** Delete Client */
      parameters: {
        query: {
          confirm_name: string;
        };
        path: {
          client_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "204": {
          content: never;
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
    patch: {
      /** Update Client */
      parameters: {
        query: never;
        path: {
          client_id: string;
        };
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["ClientPatch"];
        };
      };
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["ClientOut"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/clients/{client_id}/archive": {
    post: {
      /** Archive Client */
      parameters: {
        query: never;
        path: {
          client_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["ClientOut"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/jobs": {
    get: {
      /** List Jobs */
      parameters: {
        query: {
          client_id?: string | null;
          q?: string | null;
          state?: "ok" | "warning" | "failing" | "missed" | "unknown" | "paused" | "maintenance" | null;
          kind?: "backup" | "script" | "other" | null;
          pack?: string | null;
          archived?: boolean;
          cursor?: string | null;
          limit?: number;
        };
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["JobPage"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
    post: {
      /** Create Job */
      parameters: {
        query: never;
        path: never;
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["NewJob"];
        };
      };
      responses: {
        "201": {
          content: {
            "application/json": components["schemas"]["JobOut"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/jobs/export.csv": {
    get: {
      /** Export Jobs */
      parameters: {
        query: {
          client_id?: string | null;
        };
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "text/csv": string;
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/jobs/import.csv": {
    post: {
      /** Import Jobs */
      parameters: {
        query: {
          dry_run?: boolean;
        };
        path: never;
      };
      requestBody: {
        content: {
          "multipart/form-data": components["schemas"]["Body_import_jobs_api_v1_jobs_import_csv_post"];
        };
      };
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["ImportResult"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/jobs/{job_id}": {
    get: {
      /** Get Job */
      parameters: {
        query: never;
        path: {
          job_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["JobOut"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
    patch: {
      /** Update Job */
      parameters: {
        query: never;
        path: {
          job_id: string;
        };
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["JobPatch"];
        };
      };
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["JobOut"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/jobs/{job_id}/pause": {
    post: {
      /** Pause Job */
      parameters: {
        query: never;
        path: {
          job_id: string;
        };
      };
      requestBody?: {
        content: {
          "application/json": components["schemas"]["PauseRequest"] | null;
        };
      };
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["JobOut"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/jobs/{job_id}/resume": {
    post: {
      /** Resume Job */
      parameters: {
        query: never;
        path: {
          job_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["JobOut"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/jobs/{job_id}/archive": {
    post: {
      /** Archive Job */
      parameters: {
        query: never;
        path: {
          job_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["JobOut"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/schedule/preview": {
    post: {
      /** Preview Schedule */
      parameters: {
        query: never;
        path: never;
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["SchedulePreviewRequest"];
        };
      };
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["SchedulePreview"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/inboxes": {
    get: {
      /** List Inboxes */
      parameters: {
        query: {
          kind?: "smtp" | "imap" | "webhook" | "upload" | null;
          cursor?: string | null;
          limit?: number;
        };
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["InboxPage"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
    post: {
      /** Create Inbox */
      parameters: {
        query: never;
        path: never;
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["NewInbox"];
        };
      };
      responses: {
        "201": {
          content: {
            "application/json": components["schemas"]["InboxCreated"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/inboxes/{inbox_id}": {
    get: {
      /** Get Inbox */
      parameters: {
        query: never;
        path: {
          inbox_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["InboxOut"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
    delete: {
      /** Delete Inbox */
      parameters: {
        query: never;
        path: {
          inbox_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "204": {
          content: never;
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
    patch: {
      /** Update Inbox */
      parameters: {
        query: never;
        path: {
          inbox_id: string;
        };
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["InboxPatch"];
        };
      };
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["InboxOut"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/inboxes/{inbox_id}/token": {
    post: {
      /** Rotate Inbox Token */
      parameters: {
        query: never;
        path: {
          inbox_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["InboxToken"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/messages": {
    get: {
      /** List Messages */
      parameters: {
        query: {
          inbox_id?: string | null;
          parse_state?: "pending" | "parsed" | "unmatched" | "error" | null;
          cursor?: string | null;
          limit?: number;
        };
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["MessagePage"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/messages/{message_id}": {
    get: {
      /** Get Message */
      parameters: {
        query: never;
        path: {
          message_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["MessageDetail"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/results": {
    get: {
      /** List Results */
      parameters: {
        query: {
          job_id?: string | null;
          status?: "success" | "warning" | "failed" | "started" | "unknown" | null;
          cursor?: string | null;
          limit?: number;
        };
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["ResultPage"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/jobs/{job_id}/results": {
    get: {
      /** List Job Results */
      parameters: {
        query: {
          status?: "success" | "warning" | "failed" | "started" | "unknown" | null;
          cursor?: string | null;
          limit?: number;
        };
        path: {
          job_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["ResultPage"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
  "/api/v1/system/status": {
    get: {
      /** System Status */
      parameters: {
        query: never;
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["SystemStatus"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
  };
}

export interface components {
  schemas: {
    Body_import_jobs_api_v1_jobs_import_csv_post: {
      /** The CSV file (UTF-8). */
      file: string;
    };
    ClientOut: {
      id: string;
      name: string;
      notes: string;
      aliases: string[];
      archived: boolean;
      created_at: string;
      job_count: number;
      status_counts: Record<string, number>;
      worst_state: "ok" | "warning" | "failing" | "missed" | "unknown" | "paused" | "maintenance" | null;
    };
    ClientPage: {
      items: components["schemas"]["ClientOut"][];
      next_cursor: string | null;
    };
    /** Only the fields sent change. */
    ClientPatch: {
      name?: string | null;
      notes?: string | null;
      aliases?: string[] | null;
      archived?: boolean | null;
    };
    /** The new token with its value. The value is shown this once only. */
    CreatedToken: {
      id: string;
      label: string;
      scope: "ingest" | "read";
      created_by: string | null;
      created_at: string;
      last_used_at: string | null;
      revoked_at: string | null;
      token: string;
    };
    Credentials: {
      email: string;
      password: string;
    };
    /** One invalid input: where it is (for example body.email) and why. */
    FieldProblem: {
      field: string;
      message: string;
    };
    HeaderOut: {
      name: string;
      value: string;
    };
    ImapOut: {
      host: string | null;
      port: number | null;
      username: string | null;
      folder: string | null;
      poll_seconds: number | null;
      tls: boolean | null;
      secret_set: boolean;
      secret_hint: string | null;
    };
    /** Only the fields sent change; a password replaces the stored one. */
    ImapPatch: {
      host?: string | null;
      port?: number | null;
      username?: string | null;
      password?: string | null;
      folder?: string | null;
      poll_seconds?: number | null;
      tls?: boolean | null;
    };
    /** A mailbox the MSP already collects alert mail in. */
    ImapSettings: {
      host: string;
      port?: number;
      username: string;
      password: string;
      folder?: string;
      poll_seconds?: number;
      tls?: boolean;
    };
    /** A row that was not imported. Row 1 is the header line. */
    ImportProblem: {
      row: number;
      message: string;
    };
    ImportResult: {
      created: number;
      updated: number;
      clients_created: number;
      errors: components["schemas"]["ImportProblem"][];
      dry_run: boolean;
    };
    InboxActivity: {
      id: string;
      kind: "smtp" | "imap" | "webhook" | "upload";
      label: string;
      last_message_at: string | null;
    };
    /** The new inbox; webhook_token is in this answer only (webhook inboxes). */
    InboxCreated: {
      id: string;
      kind: "smtp" | "imap" | "webhook" | "upload";
      label: string;
      address: string | null;
      ingest_url: string | null;
      imap: components["schemas"]["ImapOut"] | null;
      webhook_token_set: boolean;
      sender_allowlist: string[];
      require_auth_results: boolean;
      created_at: string;
      updated_at: string;
      last_message_at: string | null;
      webhook_token: string | null;
    };
    InboxOut: {
      id: string;
      kind: "smtp" | "imap" | "webhook" | "upload";
      label: string;
      address: string | null;
      ingest_url: string | null;
      imap: components["schemas"]["ImapOut"] | null;
      webhook_token_set: boolean;
      sender_allowlist: string[];
      require_auth_results: boolean;
      created_at: string;
      updated_at: string;
      last_message_at: string | null;
    };
    InboxPage: {
      items: components["schemas"]["InboxOut"][];
      next_cursor: string | null;
    };
    /** Only the fields sent change. The kind and the code never change. */
    InboxPatch: {
      label?: string | null;
      imap?: components["schemas"]["ImapPatch"] | null;
      sender_allowlist?: string[] | null;
      require_auth_results?: boolean | null;
    };
    /** A webhook inbox's new token, shown this once; the old one stops working. */
    InboxToken: {
      webhook_token: string;
    };
    /** A job; its state is paused or unknown until the evaluator keeps it (C7). */
    JobOut: {
      id: string;
      client_id: string;
      client_name: string;
      name: string;
      kind: "backup" | "script" | "other";
      parser_pack_id: string | null;
      match_key: string | null;
      schedule_kind: "cron" | "interval" | "daily";
      schedule_expr: string;
      timezone: string;
      max_runtime_minutes: number;
      grace_minutes: number;
      escalate_minutes: number;
      attribution_basis: "started" | "finished" | "received";
      warning_policy: "warning_is_attention" | "warning_counts_ok";
      consecutive_failures_to_alert: number;
      ping_url: string | null;
      enabled: boolean;
      paused_until: string | null;
      archived: boolean;
      state: "ok" | "warning" | "failing" | "missed" | "unknown" | "paused" | "maintenance";
      state_since: string | null;
      last_success_at: string | null;
      acknowledged_at: string | null;
      created_at: string;
      updated_at: string;
    };
    JobPage: {
      items: components["schemas"]["JobOut"][];
      next_cursor: string | null;
    };
    /** Only the fields sent change; null clears parser_pack_id and match_key. */
    JobPatch: {
      client_id?: string | null;
      name?: string | null;
      kind?: "backup" | "script" | "other" | null;
      parser_pack_id?: string | null;
      match_key?: string | null;
      schedule_kind?: "cron" | "interval" | "daily" | null;
      schedule_expr?: string | null;
      timezone?: string | null;
      max_runtime_minutes?: number | null;
      grace_minutes?: number | null;
      escalate_minutes?: number | null;
      attribution_basis?: "started" | "finished" | "received" | null;
      warning_policy?: "warning_is_attention" | "warning_counts_ok" | null;
      consecutive_failures_to_alert?: number | null;
      enabled?: boolean | null;
      archived?: boolean | null;
    };
    Me: {
      id: string;
      email: string;
      role: "admin" | "technician";
      csrf_token: string;
    };
    MessageDetail: {
      id: string;
      inbox_id: string | null;
      client_id: string | null;
      received_at: string;
      message_id: string | null;
      size: number;
      parse_state: "pending" | "parsed" | "unmatched" | "error";
      subject: string | null;
      sender: string | null;
      headers: components["schemas"]["HeaderOut"][];
      text: string;
      text_truncated: boolean;
      results: components["schemas"]["ResultOut"][];
    };
    MessageOut: {
      id: string;
      inbox_id: string | null;
      client_id: string | null;
      received_at: string;
      message_id: string | null;
      size: number;
      parse_state: "pending" | "parsed" | "unmatched" | "error";
      subject: string | null;
      sender: string | null;
    };
    MessagePage: {
      items: components["schemas"]["MessageOut"][];
      next_cursor: string | null;
    };
    NewAccount: {
      email: string;
      password: string;
    };
    NewClient: {
      name: string;
      notes?: string;
      aliases?: string[];
    };
    NewInbox: {
      kind: "smtp" | "imap" | "webhook" | "upload";
      label: string;
      imap?: components["schemas"]["ImapSettings"] | null;
      sender_allowlist?: string[];
      require_auth_results?: boolean;
    };
    NewJob: {
      kind?: "backup" | "script" | "other";
      parser_pack_id?: string | null;
      match_key?: string | null;
      schedule_kind: "cron" | "interval" | "daily";
      schedule_expr: string;
      timezone: string;
      max_runtime_minutes?: number;
      grace_minutes?: number;
      escalate_minutes?: number;
      attribution_basis?: "started" | "finished" | "received";
      warning_policy?: "warning_is_attention" | "warning_counts_ok";
      consecutive_failures_to_alert?: number;
      client_id: string;
      name: string;
      enabled?: boolean;
    };
    NewToken: {
      label: string;
      scope: "ingest" | "read";
    };
    NewUser: {
      email: string;
      password: string;
      role: "admin" | "technician";
    };
    /** Without until the job stays paused until it is resumed. */
    PauseRequest: {
      until?: string | null;
    };
    /** An RFC 9457 problem details document. */
    Problem: {
      type?: string;
      title: string;
      status: number;
      detail?: string | null;
      instance?: string | null;
      request_id?: string | null;
      errors?: components["schemas"]["FieldProblem"][] | null;
    };
    QueueStatus: {
      pending_messages: number;
    };
    ResultOut: {
      id: string;
      job_id: string | null;
      client_hint: string | null;
      job_name: string | null;
      status: "success" | "warning" | "failed" | "started" | "unknown";
      started_at: string | null;
      finished_at: string | null;
      received_at: string;
      raw_message_id: string | null;
      run_id: string | null;
      details: Record<string, unknown>;
    };
    ResultPage: {
      items: components["schemas"]["ResultOut"][];
      next_cursor: string | null;
    };
    /** The next times, or why the schedule cannot be used (error and field). */
    SchedulePreview: {
      next: string[];
      local: string[];
      error: string | null;
      field: string | null;
    };
    SchedulePreviewRequest: {
      kind: "cron" | "interval" | "daily";
      expr: string;
      timezone: string;
      count?: number;
      anchor?: string | null;
      after?: string | null;
    };
    SetupState: {
      needs_first_run: boolean;
    };
    SignedIn: {
      user: components["schemas"]["UserOut"];
      csrf_token: string;
    };
    SystemStatus: {
      worker: components["schemas"]["WorkerStatus"];
      inboxes: components["schemas"]["InboxActivity"][];
      queue: components["schemas"]["QueueStatus"];
      version: string;
      revision: string | null;
    };
    TokenOut: {
      id: string;
      label: string;
      scope: "ingest" | "read";
      created_by: string | null;
      created_at: string;
      last_used_at: string | null;
      revoked_at: string | null;
    };
    TokenPage: {
      items: components["schemas"]["TokenOut"][];
      next_cursor: string | null;
    };
    UserOut: {
      id: string;
      email: string;
      role: "admin" | "technician";
      disabled: boolean;
      locked_until: string | null;
      created_at: string;
    };
    UserPage: {
      items: components["schemas"]["UserOut"][];
      next_cursor: string | null;
    };
    /** Only the fields sent change. A new password also clears a lockout. */
    UserPatch: {
      role?: "admin" | "technician" | null;
      disabled?: boolean | null;
      password?: string | null;
    };
    WorkerStatus: {
      heartbeat_at: string | null;
      age_seconds: number | null;
      stale: boolean;
      holder: string | null;
      started_at: string | null;
    };
  };
}

export type operations = {
  healthz_healthz_get: paths["/healthz"]["get"];
  readyz_readyz_get: paths["/readyz"]["get"];
  setup_state_api_v1_auth_setup_state_get: paths["/api/v1/auth/setup-state"]["get"];
  first_run_state_api_v1_auth_first_run_get: paths["/api/v1/auth/first-run"]["get"];
  first_run_api_v1_auth_first_run_post: paths["/api/v1/auth/first-run"]["post"];
  login_api_v1_auth_login_post: paths["/api/v1/auth/login"]["post"];
  logout_api_v1_auth_logout_post: paths["/api/v1/auth/logout"]["post"];
  me_api_v1_auth_me_get: paths["/api/v1/auth/me"]["get"];
  list_users_api_v1_users_get: paths["/api/v1/users"]["get"];
  create_user_api_v1_users_post: paths["/api/v1/users"]["post"];
  get_user_api_v1_users__user_id__get: paths["/api/v1/users/{user_id}"]["get"];
  delete_user_api_v1_users__user_id__delete: paths["/api/v1/users/{user_id}"]["delete"];
  update_user_api_v1_users__user_id__patch: paths["/api/v1/users/{user_id}"]["patch"];
  list_tokens_api_v1_tokens_get: paths["/api/v1/tokens"]["get"];
  create_token_api_v1_tokens_post: paths["/api/v1/tokens"]["post"];
  revoke_token_api_v1_tokens__token_id__delete: paths["/api/v1/tokens/{token_id}"]["delete"];
  list_clients_api_v1_clients_get: paths["/api/v1/clients"]["get"];
  create_client_api_v1_clients_post: paths["/api/v1/clients"]["post"];
  get_client_api_v1_clients__client_id__get: paths["/api/v1/clients/{client_id}"]["get"];
  delete_client_api_v1_clients__client_id__delete: paths["/api/v1/clients/{client_id}"]["delete"];
  update_client_api_v1_clients__client_id__patch: paths["/api/v1/clients/{client_id}"]["patch"];
  archive_client_api_v1_clients__client_id__archive_post: paths["/api/v1/clients/{client_id}/archive"]["post"];
  list_jobs_api_v1_jobs_get: paths["/api/v1/jobs"]["get"];
  create_job_api_v1_jobs_post: paths["/api/v1/jobs"]["post"];
  export_jobs_api_v1_jobs_export_csv_get: paths["/api/v1/jobs/export.csv"]["get"];
  import_jobs_api_v1_jobs_import_csv_post: paths["/api/v1/jobs/import.csv"]["post"];
  get_job_api_v1_jobs__job_id__get: paths["/api/v1/jobs/{job_id}"]["get"];
  update_job_api_v1_jobs__job_id__patch: paths["/api/v1/jobs/{job_id}"]["patch"];
  pause_job_api_v1_jobs__job_id__pause_post: paths["/api/v1/jobs/{job_id}/pause"]["post"];
  resume_job_api_v1_jobs__job_id__resume_post: paths["/api/v1/jobs/{job_id}/resume"]["post"];
  archive_job_api_v1_jobs__job_id__archive_post: paths["/api/v1/jobs/{job_id}/archive"]["post"];
  preview_schedule_api_v1_schedule_preview_post: paths["/api/v1/schedule/preview"]["post"];
  list_inboxes_api_v1_inboxes_get: paths["/api/v1/inboxes"]["get"];
  create_inbox_api_v1_inboxes_post: paths["/api/v1/inboxes"]["post"];
  get_inbox_api_v1_inboxes__inbox_id__get: paths["/api/v1/inboxes/{inbox_id}"]["get"];
  delete_inbox_api_v1_inboxes__inbox_id__delete: paths["/api/v1/inboxes/{inbox_id}"]["delete"];
  update_inbox_api_v1_inboxes__inbox_id__patch: paths["/api/v1/inboxes/{inbox_id}"]["patch"];
  rotate_inbox_token_api_v1_inboxes__inbox_id__token_post: paths["/api/v1/inboxes/{inbox_id}/token"]["post"];
  list_messages_api_v1_messages_get: paths["/api/v1/messages"]["get"];
  get_message_api_v1_messages__message_id__get: paths["/api/v1/messages/{message_id}"]["get"];
  list_results_api_v1_results_get: paths["/api/v1/results"]["get"];
  list_job_results_api_v1_jobs__job_id__results_get: paths["/api/v1/jobs/{job_id}/results"]["get"];
  system_status_api_v1_system_status_get: paths["/api/v1/system/status"]["get"];
};
