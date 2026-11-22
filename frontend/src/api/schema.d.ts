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
  "/api/v1/jobs/{job_id}/acknowledge": {
    post: {
      /** Acknowledge Job */
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
    post: {
      /** Create Result */
      parameters: {
        query: never;
        path: never;
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["NewResult"];
        };
      };
      responses: {
        "202": {
          content: {
            "application/json": components["schemas"]["ResultAccepted"];
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
  "/api/v1/jobs/{job_id}/occurrences": {
    get: {
      /** List Occurrences */
      parameters: {
        query: {
          from?: string | null;
          to?: string | null;
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
            "application/json": components["schemas"]["OccurrencePage"];
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
  "/api/v1/flips": {
    get: {
      /** List Flips */
      parameters: {
        query: {
          job_id?: string | null;
          client_id?: string | null;
          since?: string | null;
          cursor?: string | null;
          limit?: number;
        };
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["FlipPage"];
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
  "/api/v1/ingest/email/{inbox_code}": {
    post: {
      /** Ingest Email */
      parameters: {
        query: never;
        path: {
          inbox_code: string;
        };
      };
      requestBody: {
        content: {
          "message/rfc822": string;
        };
      };
      responses: {
        "202": {
          content: {
            "application/json": components["schemas"]["MessageAccepted"];
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
  "/api/v1/ping/{ping_token}": {
    get: {
      /** Ping Success */
      parameters: {
        query: never;
        path: {
          ping_token: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "text/plain": string;
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
      /** Ping Success */
      parameters: {
        query: never;
        path: {
          ping_token: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "text/plain": string;
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
  "/api/v1/ping/{ping_token}/{signal}": {
    get: {
      /** Ping Signal */
      parameters: {
        query: never;
        path: {
          ping_token: string;
          signal: "start" | "fail";
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "text/plain": string;
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
      /** Ping Signal */
      parameters: {
        query: never;
        path: {
          ping_token: string;
          signal: "start" | "fail";
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "text/plain": string;
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
  "/api/v1/messages/upload": {
    post: {
      /** Upload Message */
      parameters: {
        query: never;
        path: never;
      };
      requestBody: {
        content: {
          "multipart/form-data": components["schemas"]["Body_upload_message_api_v1_messages_upload_post"];
        };
      };
      responses: {
        "202": {
          content: {
            "application/json": components["schemas"]["MessageAccepted"];
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
  "/api/v1/packs": {
    get: {
      /** List Packs */
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
            "application/json": components["schemas"]["PackPage"];
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
  "/api/v1/packs/import": {
    post: {
      /** Import Pack */
      parameters: {
        query: never;
        path: never;
      };
      requestBody: {
        content: {
          "multipart/form-data": components["schemas"]["Body_import_pack_api_v1_packs_import_post"];
        };
      };
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["PackDetail"];
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
  "/api/v1/packs/test": {
    post: {
      /** Test Pack */
      parameters: {
        query: never;
        path: never;
      };
      requestBody: {
        content: {
          "application/json": {
            raw: string;
            pack?: string | null;
          };
        };
      };
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["PackTestAnswer"];
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
  "/api/v1/packs/{pack_id}": {
    get: {
      /** Get Pack */
      parameters: {
        query: never;
        path: {
          pack_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["PackDetail"];
          };
        };
        "4XX": {
          content: {
            "application/problem+json": components["schemas"]["Problem"];
          };
        };
      };
    };
    put: {
      /** Put Pack */
      parameters: {
        query: never;
        path: {
          pack_id: string;
        };
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["PackBody"];
        };
      };
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["PackDetail"];
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
  "/api/v1/packs/{pack_id}/export": {
    get: {
      /** Export Pack */
      parameters: {
        query: never;
        path: {
          pack_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/yaml": string;
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
  "/api/v1/packs/{pack_id}/enable": {
    post: {
      /** Enable Pack */
      parameters: {
        query: never;
        path: {
          pack_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["PackOut"];
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
  "/api/v1/packs/{pack_id}/disable": {
    post: {
      /** Disable Pack */
      parameters: {
        query: never;
        path: {
          pack_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["PackOut"];
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
  "/api/v1/unmatched": {
    get: {
      /** List Unmatched */
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
            "application/json": components["schemas"]["UnmatchedPage"];
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
  "/api/v1/unmatched/{result_id}/assign": {
    post: {
      /** Assign */
      parameters: {
        query: never;
        path: {
          result_id: string;
        };
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["AssignRequest"];
        };
      };
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["Binding"];
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
  "/api/v1/unmatched/{result_id}/suggest-schedule": {
    get: {
      /** Suggest Schedule */
      parameters: {
        query: {
          timezone?: string | null;
        };
        path: {
          result_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["ScheduleSuggestion"];
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
  "/api/v1/unmatched/{result_id}/create-job": {
    post: {
      /** Create Job */
      parameters: {
        query: never;
        path: {
          result_id: string;
        };
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["CreateJobRequest"];
        };
      };
      responses: {
        "201": {
          content: {
            "application/json": components["schemas"]["JobFromResult"];
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
  "/api/v1/dashboard/today": {
    get: {
      /** Dashboard Today */
      parameters: {
        query: never;
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["DashboardToday"];
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
  "/api/v1/dashboard/ribbon": {
    get: {
      /** Dashboard Ribbon */
      parameters: {
        query: {
          from?: string | null;
          to?: string | null;
          problems_only?: boolean;
        };
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["Ribbon"];
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
  "/api/v1/dashboard/trend": {
    get: {
      /** Dashboard Trend */
      parameters: {
        query: {
          days?: number;
        };
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["Trend"];
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
  "/api/v1/dashboard/breakdown": {
    get: {
      /** Dashboard Breakdown */
      parameters: {
        query: {
          by?: "vendor" | "client";
          days?: number;
        };
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["Breakdown"];
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
  "/api/v1/activity": {
    get: {
      /** List Activity */
      parameters: {
        query: {
          kind?: "ingest" | "flip" | "notification" | "config" | null;
          cursor?: string | null;
          limit?: number;
        };
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["ActivityPage"];
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
  "/api/v1/digest/preview": {
    get: {
      /** Digest Preview */
      parameters: {
        query: {
          date?: string | null;
        };
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["DigestPreview"];
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
  "/api/v1/exports/day.csv": {
    get: {
      /** Export Day */
      parameters: {
        query: {
          date?: string | null;
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
  "/api/v1/exports/history.csv": {
    get: {
      /** Export History */
      parameters: {
        query: {
          from?: string | null;
          to?: string | null;
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
  "/api/v1/clients/{client_id}/export.csv": {
    get: {
      /** Export Client */
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
  "/api/v1/channels": {
    get: {
      /** List Channels */
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
            "application/json": components["schemas"]["ChannelPage"];
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
      /** Create Channel */
      parameters: {
        query: never;
        path: never;
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["NewChannel"];
        };
      };
      responses: {
        "201": {
          content: {
            "application/json": components["schemas"]["ChannelOut"];
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
  "/api/v1/channels/check-url": {
    post: {
      /** Check Url */
      parameters: {
        query: never;
        path: never;
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["TargetCheck"];
        };
      };
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["TargetCheckResult"];
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
  "/api/v1/channels/{channel_id}": {
    get: {
      /** Get Channel */
      parameters: {
        query: never;
        path: {
          channel_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["ChannelOut"];
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
      /** Delete Channel */
      parameters: {
        query: never;
        path: {
          channel_id: string;
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
      /** Update Channel */
      parameters: {
        query: never;
        path: {
          channel_id: string;
        };
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["ChannelPatch"];
        };
      };
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["ChannelOut"];
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
  "/api/v1/channels/{channel_id}/test": {
    post: {
      /** Test Channel */
      parameters: {
        query: never;
        path: {
          channel_id: string;
        };
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["ChannelTestResult"];
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
  "/api/v1/channel-rules": {
    get: {
      /** List Rules */
      parameters: {
        query: {
          channel_id?: string | null;
          cursor?: string | null;
          limit?: number;
        };
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["RulePage"];
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
      /** Create Rule */
      parameters: {
        query: never;
        path: never;
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["NewRule"];
        };
      };
      responses: {
        "201": {
          content: {
            "application/json": components["schemas"]["RuleOut"];
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
  "/api/v1/channel-rules/{rule_id}": {
    delete: {
      /** Delete Rule */
      parameters: {
        query: never;
        path: {
          rule_id: string;
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
      /** Update Rule */
      parameters: {
        query: never;
        path: {
          rule_id: string;
        };
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["RulePatch"];
        };
      };
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["RuleOut"];
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
  "/api/v1/notifications": {
    get: {
      /** List Notifications */
      parameters: {
        query: {
          status?: "queued" | "sent" | "retrying" | "failed" | null;
          channel_id?: string | null;
          cursor?: string | null;
          limit?: number;
        };
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["NotificationPage"];
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
  "/api/v1/settings": {
    get: {
      /** Get Settings */
      parameters: {
        query: never;
        path: never;
      };
      requestBody?: never;
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["DigestSettingsOut"];
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
      /** Update Settings */
      parameters: {
        query: never;
        path: never;
      };
      requestBody: {
        content: {
          "application/json": components["schemas"]["DigestSettingsPatch"];
        };
      };
      responses: {
        "200": {
          content: {
            "application/json": components["schemas"]["DigestSettingsOut"];
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
    /** Who acknowledged the job's state. email is null for an API token: only
signed-in users see addresses. */
    AcknowledgedBy: {
      id: string;
      email: string | null;
    };
    /** One entry of the timeline. ref_kind and ref_id point to what it is
about (job, message, or the target of a configuration change). */
    ActivityItem: {
      id: string;
      at: string;
      kind: "ingest" | "flip" | "notification" | "config";
      summary: string;
      ref_kind: string | null;
      ref_id: string | null;
    };
    ActivityPage: {
      items: components["schemas"]["ActivityItem"][];
      next_cursor: string | null;
    };
    /** replace_match_key: a job whose match key names another job name takes
the result's job name instead (the old key is answered and audited). */
    AssignRequest: {
      job_id: string;
      replace_match_key?: boolean;
    };
    /** A job that needs a look. expected_by is the deadline of its newest due
run; raw_message_id the message of the result that decided that run (none
for a silent run or a ping). */
    AttentionItem: {
      client_id: string;
      client_name: string;
      job_id: string;
      job_name: string;
      state: "missed" | "overdue" | "failed" | "warning";
      expected_by: string | null;
      last_success_at: string | null;
      raw_message_id: string | null;
      acknowledged_at: string | null;
    };
    /** The mail as the engine reads it: decoded headers and the visible text
(HTML as text, at most 256 KiB). Span offsets point into these. */
    BenchMail: {
      sender: string;
      to: string;
      subject: string;
      body: string;
      sent_at: string | null;
    };
    BenchResult: {
      status: "success" | "warning" | "failed" | "started" | "unknown";
      job_name: string | null;
      client_hint: string | null;
      started_at: string | null;
      finished_at: string | null;
      run_id: string | null;
      details: Record<string, string>;
      spans: components["schemas"]["BenchSpan"][];
    };
    BenchScore: {
      pack_id: string;
      matched: number;
    };
    /** A pack left out: invalid, a stored pack that no longer loads (path
null); timeout, deadline or memory, a pack whose claim failed at path
(the other packs still compete for the mail). */
    BenchSkipped: {
      pack_id: string;
      reason: "invalid" | "timeout" | "deadline" | "memory";
      path: string | null;
    };
    /** Characters start to end of source (body, subject, from or to) hold the
value of field (job_name, details.size, status, ...). */
    BenchSpan: {
      field: string;
      start: number;
      end: number;
      source: string;
    };
    /** The result is bound to job_id.

match_key_set: the job's match key is now the result's job name (it had
none, or replace_match_key replaced replaced_match_key). current_match_key:
the job's match key after the call; when match_key_set is false and it
names another job name, the next identical mail binds only if the job's
name is that job name. client_alias_added: the result's client hint became
an alias of the client; else reason says why not (no_client_hint,
already_known, alias_of_other_client, alias_limit). also_bound: other
unmatched results with the same names bound as well. */
    Binding: {
      result_id: string;
      job_id: string;
      client_id: string;
      match_key_set: boolean;
      current_match_key: string | null;
      replaced_match_key: string | null;
      client_alias_added: boolean;
      reason: "no_client_hint" | "already_known" | "alias_of_other_client" | "alias_limit" | null;
      also_bound: number;
    };
    Body_import_jobs_api_v1_jobs_import_csv_post: {
      /** The CSV file (UTF-8). */
      file: string;
    };
    Body_import_pack_api_v1_packs_import_post: {
      /** The Pack YAML file. */
      file: string;
    };
    Body_upload_message_api_v1_messages_upload_post: {
      /** The message as an .eml file. */
      file: string;
      inbox_id: string;
    };
    Breakdown: {
      by: "vendor" | "client";
      items: components["schemas"]["BreakdownItem"][];
    };
    /** key: the parser pack id (none for jobs without a pack) or the client
id; label: the pack's vendor or the client's name. */
    BreakdownItem: {
      key: string;
      label: string;
      verified: number;
      failed: number;
      silent: number;
    };
    ChannelOut: {
      id: string;
      kind: "email" | "slack" | "teams" | "webhook";
      label: string;
      enabled: boolean;
      config: Record<string, unknown>;
      available: boolean;
      secret_label: string | null;
      secret_set: boolean;
      secret_hint: string | null;
      last_status: "sent" | "failed" | null;
      last_status_at: string | null;
      last_error: string | null;
      created_at: string;
      updated_at: string;
    };
    ChannelPage: {
      items: components["schemas"]["ChannelOut"][];
      next_cursor: string | null;
    };
    /** Only the fields sent change. config keys sent replace the stored ones
(a null removes the key) and the result is checked again. A secret sent
replaces the stored one; an empty secret removes it. Changing a setting
that decides where the secret goes needs the secret again (422). */
    ChannelPatch: {
      label?: string | null;
      enabled?: boolean | null;
      config?: Record<string, unknown> | null;
      secret?: string | null;
    };
    /** ok: the test message was delivered; detail says what happened. */
    ChannelTestResult: {
      ok: boolean;
      detail: string;
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
    /** Due runs of the last 24 hours that were verified; ratio is null when
none was due. */
    Coverage: {
      verified: number;
      expected: number;
      ratio: number | null;
    };
    /** A job made from an unmatched result, for an existing client (client_id)
or a client by name (client_name: found, or created). name defaults to the
result's job name and match_key to it as well. Without schedule_kind and
schedule_expr the job runs daily at the time suggest-schedule gives (from
one result on); timezone defaults to the digest time zone of Settings. */
    CreateJobRequest: {
      client_id?: string | null;
      client_name?: string | null;
      name?: string | null;
      kind?: "backup" | "script" | "other";
      parser_pack_id?: string | null;
      match_key?: string | null;
      schedule_kind?: "cron" | "interval" | "daily" | null;
      schedule_expr?: string | null;
      timezone?: string | null;
      max_runtime_minutes?: number;
      grace_minutes?: number;
      escalate_minutes?: number;
      attribution_basis?: "started" | "finished" | "received";
      warning_policy?: "warning_is_attention" | "warning_counts_ok";
      consecutive_failures_to_alert?: number;
      enabled?: boolean;
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
    DashboardToday: {
      generated_at: string;
      stats: components["schemas"]["Stats"];
      coverage: components["schemas"]["Coverage"];
      attention: components["schemas"]["AttentionItem"][];
      heartbeat: components["schemas"]["HeartbeatOut"];
      demo_seeded: boolean;
    };
    /** The morning digest of date as it would be sent. */
    DigestPreview: {
      date: string;
      subject: string;
      html: string;
      text: string;
    };
    /** When the daily digest goes out (HH:MM in the zone) and whether a
24-hour reminder follows a failing or missed job. */
    DigestSettingsOut: {
      digest_time_local: string;
      digest_timezone: string;
      reminder_24h: boolean;
    };
    /** Only the fields sent change; at least one must be sent. */
    DigestSettingsPatch: {
      digest_time_local?: string | null;
      digest_timezone?: string | null;
      reminder_24h?: boolean | null;
    };
    /** One invalid input: where it is (for example body.email) and why. */
    FieldProblem: {
      field: string;
      message: string;
    };
    /** One change of a job's state; the single source of alerts. */
    FlipOut: {
      id: string;
      job_id: string;
      client_id: string;
      from_state: "ok" | "warning" | "failing" | "missed" | "unknown" | "paused" | "maintenance";
      to_state: "ok" | "warning" | "failing" | "missed" | "unknown" | "paused" | "maintenance";
      reason: string;
      at: string;
    };
    FlipPage: {
      items: components["schemas"]["FlipOut"][];
      next_cursor: string | null;
    };
    HeaderOut: {
      name: string;
      value: string;
    };
    /** The worker heartbeat; stale when older than 3 minutes or missing. */
    HeartbeatOut: {
      at: string | null;
      age_seconds: number | null;
      stale: boolean;
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
    JobFromResult: {
      job: components["schemas"]["JobOut"];
      client_created: boolean;
      binding: components["schemas"]["Binding"];
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
      acknowledged_by?: components["schemas"]["AcknowledgedBy"] | null;
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
    /** The stored message, or for a duplicate the earlier one; the worker
parses it (parse_state pending). */
    MessageAccepted: {
      message_id: string;
      duplicate: boolean;
    };
    MessageDetail: {
      id: string;
      inbox_id: string | null;
      client_id: string | null;
      received_at: string;
      message_id: string | null;
      size: number;
      parse_state: "pending" | "parsed" | "unmatched" | "error";
      parsed_at: string | null;
      parse_pack_id: string | null;
      parse_reason: string | null;
      parse_path: string | null;
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
      parsed_at: string | null;
      parse_pack_id: string | null;
      parse_reason: string | null;
      parse_path: string | null;
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
    /** A channel. config is the kind's settings (docs/notifications.md);
secret is its credential (the relay password), stored encrypted. */
    NewChannel: {
      kind: "email" | "slack" | "teams" | "webhook";
      label: string;
      enabled?: boolean;
      config?: Record<string, unknown>;
      secret?: string | null;
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
    /** A run reported by a script (POST results). The job is named by job_id,
by ping_token, or by client_hint and job_name for the matcher. */
    NewResult: {
      status: "success" | "warning" | "failed" | "started" | "unknown";
      job_id?: string | null;
      ping_token?: string | null;
      job_name?: string | null;
      client_hint?: string | null;
      started_at?: string | null;
      finished_at?: string | null;
      run_id?: string | null;
      details?: Record<string, unknown>;
    };
    /** scope all covers every job (scope_id null); client and job need the
client's or the job's id. digest is for scope all only. */
    NewRule: {
      channel_id: string;
      scope?: "all" | "client" | "job";
      scope_id?: string | null;
      events: ("failing" | "missed" | "warning" | "recovered" | "digest")[];
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
    /** One notification: about a flip (failing, missed, warning, recovered,
reminder; flip_id, job and client set) or the digest of digest_day. */
    NotificationOut: {
      id: string;
      channel_id: string;
      channel_label: string;
      channel_kind: "email" | "slack" | "teams" | "webhook";
      event: "failing" | "missed" | "warning" | "recovered" | "reminder" | "digest";
      status: "queued" | "sent" | "retrying" | "failed";
      attempts: number;
      error: string | null;
      flip_id: string | null;
      job_id: string | null;
      job_name: string | null;
      client_id: string | null;
      client_name: string | null;
      digest_day: string | null;
      created_at: string;
      last_attempt_at: string | null;
      next_attempt_at: string | null;
      sent_at: string | null;
    };
    NotificationPage: {
      items: components["schemas"]["NotificationOut"][];
      next_cursor: string | null;
    };
    /** One expected run of a job. note explains the state in a few words
(recovered after retry, late result, started, never finished). */
    OccurrenceOut: {
      job_id: string;
      scheduled_for: string;
      deadline: string;
      state: "pending" | "running" | "verified" | "warning" | "failed" | "overdue" | "missed" | "maintenance";
      result_id: string | null;
      note: string | null;
    };
    OccurrencePage: {
      items: components["schemas"]["OccurrenceOut"][];
      next_cursor: string | null;
    };
    /** A custom pack as Pack YAML; its id must be the id in the URL. */
    PackBody: {
      yaml: string;
    };
    PackDetail: {
      id: string;
      version: number;
      vendor: string;
      status: "verified" | "unverified-synthetic";
      source: "builtin" | "custom";
      enabled: boolean;
      created_at: string;
      updated_at: string;
      yaml: string;
    };
    PackOut: {
      id: string;
      version: number;
      vendor: string;
      status: "verified" | "unverified-synthetic";
      source: "builtin" | "custom";
      enabled: boolean;
      created_at: string;
      updated_at: string;
    };
    PackPage: {
      items: components["schemas"]["PackOut"][];
      next_cursor: string | null;
    };
    /** One problem of a parser pack: a JSON Pointer into the pack ("" for the
whole document) and why. */
    PackProblem: {
      path: string;
      message: string;
    };
    /** What the packs make of the mail.

scores: every pack not skipped. claimed_by: the pack that claims the
mail among the enabled packs (with the edited one), null for no claim or
a tie. outcome: parsed (results of pack_id: the edited pack when one was
sent, else the claiming pack), unmatched (reason no-pack, tie with the
candidates, or no-records) or error (reason timeout, deadline,
too-many-records or memory, at path). skipped: the packs left out. */
    PackTestAnswer: {
      mail: components["schemas"]["BenchMail"];
      scores: components["schemas"]["BenchScore"][];
      claimed_by: string | null;
      outcome: "parsed" | "unmatched" | "error";
      pack_id: string | null;
      reason: string | null;
      path: string | null;
      candidates: string[];
      results: components["schemas"]["BenchResult"][];
      skipped: components["schemas"]["BenchSkipped"][];
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
      issues?: components["schemas"]["PackProblem"][] | null;
    };
    QueueStatus: {
      pending_messages: number;
      pending_notifications: number;
      failed_notifications: number;
    };
    /** The stored result; job_id is null until the matcher binds it. */
    ResultAccepted: {
      result_id: string;
      job_id: string | null;
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
    /** The Night Ribbon: clients by name, their jobs by name, each job's runs
in the window by time. morning_line_at is the digest time in the window
(null when the window holds none). */
    Ribbon: {
      window: components["schemas"]["RibbonWindow"];
      morning_line_at: string | null;
      clients: components["schemas"]["RibbonClient"][];
    };
    RibbonClient: {
      id: string;
      name: string;
      jobs: components["schemas"]["RibbonJob"][];
    };
    RibbonJob: {
      id: string;
      name: string;
      occurrences: components["schemas"]["RibbonOccurrence"][];
    };
    /** One run: pending ones after now are still expected. result_at is when
the deciding result says the run ended (finished, else received). */
    RibbonOccurrence: {
      scheduled_for: string;
      deadline: string;
      state: "pending" | "running" | "verified" | "warning" | "failed" | "overdue" | "missed" | "maintenance";
      result_at: string | null;
    };
    /** [from, to): build it with model_validate({"from": ..., "to": ...}). */
    RibbonWindow: {
      from: string;
      to: string;
    };
    RuleOut: {
      id: string;
      channel_id: string;
      scope: "all" | "client" | "job";
      scope_id: string | null;
      scope_name: string | null;
      events: ("failing" | "missed" | "warning" | "recovered" | "digest")[];
      created_at: string;
    };
    RulePage: {
      items: components["schemas"]["RuleOut"][];
      next_cursor: string | null;
    };
    /** Only the fields sent change; the result is checked as a new rule. */
    RulePatch: {
      scope?: "all" | "client" | "job" | null;
      scope_id?: string | null;
      events?: ("failing" | "missed" | "warning" | "recovered" | "digest")[] | null;
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
    /** A daily schedule at the median time of the job's runs: expr is HH:MM in
timezone; basis is the time read of each run; results how many runs. */
    ScheduleSuggestion: {
      kind: "daily";
      expr: string;
      timezone: string;
      basis: "finished" | "started" | "received";
      results: number;
    };
    SetupState: {
      needs_first_run: boolean;
    };
    SignedIn: {
      user: components["schemas"]["UserOut"];
      csrf_token: string;
    };
    /** One stat card: value now, its change against 24 hours earlier, and the
14 values of the last 14 days, oldest first (the last one is value). */
    Stat: {
      value: number;
      delta_vs_yesterday: number;
      spark14: number[];
    };
    Stats: {
      verified: components["schemas"]["Stat"];
      failed: components["schemas"]["Stat"];
      silent: components["schemas"]["Stat"];
      unmatched: components["schemas"]["Stat"];
      paused: components["schemas"]["Stat"];
    };
    SystemStatus: {
      worker: components["schemas"]["WorkerStatus"];
      inboxes: components["schemas"]["InboxActivity"][];
      queue: components["schemas"]["QueueStatus"];
      evaluator_lag_seconds: number;
      version: string;
      revision: string | null;
      extension_api_level: number;
    };
    TargetCheck: {
      url: string;
    };
    /** The URL may be called: its host, port, the addresses it resolves to
and why it is allowed. A refused URL answers 422 with the reason. */
    TargetCheckResult: {
      ok: boolean;
      host: string;
      port: number;
      addresses: string[];
      allowed_by: "public" | "allowed_host" | "allow_private";
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
    /** Oldest day first; the last day is today (so far). */
    Trend: {
      items: components["schemas"]["TrendDay"][];
    };
    /** Due runs of one calendar day in the digest zone. */
    TrendDay: {
      date: string;
      verified: number;
      failed: number;
      silent: number;
    };
    /** A result no job is bound to yet. */
    UnmatchedOut: {
      result_id: string;
      raw_message_id: string | null;
      received_at: string;
      job_name: string | null;
      client_hint: string | null;
      status: "success" | "warning" | "failed" | "started" | "unknown";
    };
    UnmatchedPage: {
      items: components["schemas"]["UnmatchedOut"][];
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
  acknowledge_job_api_v1_jobs__job_id__acknowledge_post: paths["/api/v1/jobs/{job_id}/acknowledge"]["post"];
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
  create_result_api_v1_results_post: paths["/api/v1/results"]["post"];
  list_job_results_api_v1_jobs__job_id__results_get: paths["/api/v1/jobs/{job_id}/results"]["get"];
  list_occurrences_api_v1_jobs__job_id__occurrences_get: paths["/api/v1/jobs/{job_id}/occurrences"]["get"];
  list_flips_api_v1_flips_get: paths["/api/v1/flips"]["get"];
  ingest_email_api_v1_ingest_email__inbox_code__post: paths["/api/v1/ingest/email/{inbox_code}"]["post"];
  ping_success_api_v1_ping__ping_token__get: paths["/api/v1/ping/{ping_token}"]["get"];
  ping_success_api_v1_ping__ping_token__post: paths["/api/v1/ping/{ping_token}"]["post"];
  ping_signal_api_v1_ping__ping_token___signal__get: paths["/api/v1/ping/{ping_token}/{signal}"]["get"];
  ping_signal_api_v1_ping__ping_token___signal__post: paths["/api/v1/ping/{ping_token}/{signal}"]["post"];
  upload_message_api_v1_messages_upload_post: paths["/api/v1/messages/upload"]["post"];
  list_packs_api_v1_packs_get: paths["/api/v1/packs"]["get"];
  import_pack_api_v1_packs_import_post: paths["/api/v1/packs/import"]["post"];
  test_pack_api_v1_packs_test_post: paths["/api/v1/packs/test"]["post"];
  get_pack_api_v1_packs__pack_id__get: paths["/api/v1/packs/{pack_id}"]["get"];
  put_pack_api_v1_packs__pack_id__put: paths["/api/v1/packs/{pack_id}"]["put"];
  export_pack_api_v1_packs__pack_id__export_get: paths["/api/v1/packs/{pack_id}/export"]["get"];
  enable_pack_api_v1_packs__pack_id__enable_post: paths["/api/v1/packs/{pack_id}/enable"]["post"];
  disable_pack_api_v1_packs__pack_id__disable_post: paths["/api/v1/packs/{pack_id}/disable"]["post"];
  list_unmatched_api_v1_unmatched_get: paths["/api/v1/unmatched"]["get"];
  assign_api_v1_unmatched__result_id__assign_post: paths["/api/v1/unmatched/{result_id}/assign"]["post"];
  suggest_schedule_api_v1_unmatched__result_id__suggest_schedule_get: paths["/api/v1/unmatched/{result_id}/suggest-schedule"]["get"];
  create_job_api_v1_unmatched__result_id__create_job_post: paths["/api/v1/unmatched/{result_id}/create-job"]["post"];
  system_status_api_v1_system_status_get: paths["/api/v1/system/status"]["get"];
  dashboard_today_api_v1_dashboard_today_get: paths["/api/v1/dashboard/today"]["get"];
  dashboard_ribbon_api_v1_dashboard_ribbon_get: paths["/api/v1/dashboard/ribbon"]["get"];
  dashboard_trend_api_v1_dashboard_trend_get: paths["/api/v1/dashboard/trend"]["get"];
  dashboard_breakdown_api_v1_dashboard_breakdown_get: paths["/api/v1/dashboard/breakdown"]["get"];
  list_activity_api_v1_activity_get: paths["/api/v1/activity"]["get"];
  digest_preview_api_v1_digest_preview_get: paths["/api/v1/digest/preview"]["get"];
  export_day_api_v1_exports_day_csv_get: paths["/api/v1/exports/day.csv"]["get"];
  export_history_api_v1_exports_history_csv_get: paths["/api/v1/exports/history.csv"]["get"];
  export_client_api_v1_clients__client_id__export_csv_get: paths["/api/v1/clients/{client_id}/export.csv"]["get"];
  list_channels_api_v1_channels_get: paths["/api/v1/channels"]["get"];
  create_channel_api_v1_channels_post: paths["/api/v1/channels"]["post"];
  check_url_api_v1_channels_check_url_post: paths["/api/v1/channels/check-url"]["post"];
  get_channel_api_v1_channels__channel_id__get: paths["/api/v1/channels/{channel_id}"]["get"];
  delete_channel_api_v1_channels__channel_id__delete: paths["/api/v1/channels/{channel_id}"]["delete"];
  update_channel_api_v1_channels__channel_id__patch: paths["/api/v1/channels/{channel_id}"]["patch"];
  test_channel_api_v1_channels__channel_id__test_post: paths["/api/v1/channels/{channel_id}/test"]["post"];
  list_rules_api_v1_channel_rules_get: paths["/api/v1/channel-rules"]["get"];
  create_rule_api_v1_channel_rules_post: paths["/api/v1/channel-rules"]["post"];
  delete_rule_api_v1_channel_rules__rule_id__delete: paths["/api/v1/channel-rules/{rule_id}"]["delete"];
  update_rule_api_v1_channel_rules__rule_id__patch: paths["/api/v1/channel-rules/{rule_id}"]["patch"];
  list_notifications_api_v1_notifications_get: paths["/api/v1/notifications"]["get"];
  get_settings_api_v1_settings_get: paths["/api/v1/settings"]["get"];
  update_settings_api_v1_settings_patch: paths["/api/v1/settings"]["patch"];
};
