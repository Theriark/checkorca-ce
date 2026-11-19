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
}

export interface components {
  schemas: {
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
    Me: {
      id: string;
      email: string;
      role: "admin" | "technician";
      csrf_token: string;
    };
    NewAccount: {
      email: string;
      password: string;
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
    SetupState: {
      needs_first_run: boolean;
    };
    SignedIn: {
      user: components["schemas"]["UserOut"];
      csrf_token: string;
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
};
