import {
  Plus,
  Search,
  Trash2,
  UserCheck,
  UserCog,
  UserX,
  Users,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Input,
  Modal,
  PageHeader,
  Pagination,
  Select,
  Spinner,
} from "../components/ui";
import { useAuth } from "../context/useAuth";
import { useToast } from "../context/useToast";
import { useResource } from "../hooks/useResource";
import {
  formatDate,
  formatRelativeTime,
  humanize,
  initials,
} from "../lib/utils";
import { api } from "../services/api";
import { ROLES, type Role, type User } from "../types";

const emptyForm = {
  email: "",
  display_name: "",
  password: "",
  role: "VIEWER" as Role,
};

function roleTone(role: Role): "purple" | "info" | "neutral" {
  return role === "ADMINISTRATOR"
    ? "purple"
    : role === "OPERATOR"
      ? "info"
      : "neutral";
}

export function UsersPage() {
  const { user: currentUser } = useAuth();
  const { notify } = useToast();
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [skip, setSkip] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState("");
  const [deleteUser, setDeleteUser] = useState<User | null>(null);
  const resource = useResource(
    () => api.users.list({ search, role, skip }),
    [search, role, skip],
  );

  const createUser = async (event: FormEvent) => {
    event.preventDefault();
    setFormError("");
    const email = form.email.trim().toLowerCase();
    const displayName = form.display_name.trim();
    if (!displayName) {
      setFormError("Enter a display name.");
      return;
    }
    if (displayName.length > 120) {
      setFormError("Display name must be 120 characters or fewer.");
      return;
    }
    if (form.password.length < 12 || form.password.length > 128) {
      setFormError("Password must be between 12 and 128 characters.");
      return;
    }
    if (
      !/[a-z]/.test(form.password) ||
      !/[A-Z]/.test(form.password) ||
      !/\d/.test(form.password)
    ) {
      setFormError(
        "Password must include upper-case, lower-case, and numeric characters.",
      );
      return;
    }
    setSubmitting(true);
    try {
      await api.users.create({ ...form, email, display_name: displayName });
      notify(`User ${email} created.`);
      setForm(emptyForm);
      setCreateOpen(false);
      void resource.reload();
    } catch (caught) {
      setFormError(
        caught instanceof Error ? caught.message : "User could not be created.",
      );
    } finally {
      setSubmitting(false);
    }
  };

  const updateUser = async (
    target: User,
    payload: Partial<Pick<User, "role" | "is_active">>,
  ) => {
    try {
      await api.users.update(target.id, payload);
      notify(`${target.email} updated.`);
      void resource.reload();
    } catch (caught) {
      notify(
        caught instanceof Error ? caught.message : "User could not be updated.",
        "error",
      );
    }
  };

  const removeUser = async () => {
    if (!deleteUser) return;
    setSubmitting(true);
    try {
      await api.users.remove(deleteUser.id);
      notify(`${deleteUser.email} removed.`);
      setDeleteUser(null);
      void resource.reload();
    } catch (caught) {
      notify(
        caught instanceof Error ? caught.message : "User could not be removed.",
        "error",
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="animate-slide-in">
      <PageHeader
        eyebrow="Access control"
        title="Users"
        description="Manage KANDOR identities, roles, and account status."
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> Create user
          </Button>
        }
      />
      <Card className="overflow-hidden">
        <div className="flex flex-col gap-3 border-b border-line/70 p-4 sm:flex-row">
          <div className="relative flex-1 sm:max-w-md">
            <Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-slate-600" />
            <Input
              aria-label="Search users"
              className="pl-9"
              placeholder="Search email or display name…"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setSkip(0);
              }}
            />
          </div>
          <Select
            aria-label="User role"
            className="sm:w-52"
            value={role}
            onChange={(event) => {
              setRole(event.target.value);
              setSkip(0);
            }}
          >
            <option value="">All roles</option>
            {ROLES.map((item) => (
              <option key={item} value={item}>
                {humanize(item)}
              </option>
            ))}
          </Select>
        </div>
        {resource.loading ? (
          <Spinner label="Loading identities" />
        ) : resource.error && !resource.data ? (
          <ErrorState
            error={resource.error}
            onRetry={() => void resource.reload()}
          />
        ) : resource.data?.items.length ? (
          <>
            <div className="overflow-x-auto">
              <table className="w-full" aria-label="KANDOR users">
                <thead className="border-b border-line/70 bg-void/25">
                  <tr>
                    <th className="table-heading">Identity</th>
                    <th className="table-heading">Role</th>
                    <th className="table-heading">Status</th>
                    <th className="table-heading">Last sign-in</th>
                    <th className="table-heading">Created</th>
                    <th className="table-heading">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line/50">
                  {resource.data.items.map((account) => {
                    const isSelf = account.id === currentUser?.id;
                    return (
                      <tr key={account.id} className="hover:bg-white/[.02]">
                        <td className="table-cell">
                          <div className="flex items-center gap-3">
                            <span className="grid h-8 w-8 place-items-center rounded-lg border border-line bg-void text-[10px] font-bold text-slate-400">
                              {initials(account.display_name || account.email)}
                            </span>
                            <div>
                              <p className="font-medium text-slate-200">
                                {account.display_name || "Unnamed user"}
                                {isSelf && (
                                  <span className="ml-2 text-[9px] uppercase tracking-wider text-kandor-400">
                                    You
                                  </span>
                                )}
                              </p>
                              <p className="mt-0.5 text-[11px] text-slate-600">
                                {account.email}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="table-cell">
                          <div className="flex items-center gap-2">
                            <Badge tone={roleTone(account.role)}>
                              {account.role}
                            </Badge>
                            {!isSelf && (
                              <Select
                                aria-label={`Role for ${account.email}`}
                                className="h-8 w-10 border-transparent bg-transparent px-0 text-transparent hover:border-line"
                                value={account.role}
                                onChange={(event) =>
                                  void updateUser(account, {
                                    role: event.target.value as Role,
                                  })
                                }
                              >
                                {ROLES.map((item) => (
                                  <option key={item} value={item}>
                                    {humanize(item)}
                                  </option>
                                ))}
                              </Select>
                            )}
                          </div>
                        </td>
                        <td className="table-cell">
                          <Badge
                            tone={account.is_active ? "success" : "danger"}
                          >
                            {account.is_active ? "Active" : "Suspended"}
                          </Badge>
                        </td>
                        <td className="table-cell">
                          {account.last_login_at
                            ? formatRelativeTime(account.last_login_at)
                            : "Never"}
                        </td>
                        <td className="table-cell">
                          {formatDate(account.created_at, false)}
                        </td>
                        <td className="table-cell">
                          <div className="flex justify-end gap-1">
                            {!isSelf && (
                              <>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  title={
                                    account.is_active
                                      ? "Suspend user"
                                      : "Activate user"
                                  }
                                  aria-label={`${account.is_active ? "Suspend" : "Activate"} ${account.email}`}
                                  onClick={() =>
                                    void updateUser(account, {
                                      is_active: !account.is_active,
                                    })
                                  }
                                >
                                  {account.is_active ? (
                                    <UserX className="h-3.5 w-3.5" />
                                  ) : (
                                    <UserCheck className="h-3.5 w-3.5" />
                                  )}
                                </Button>
                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="hover:text-red-300"
                                  aria-label={`Remove ${account.email}`}
                                  onClick={() => setDeleteUser(account)}
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </Button>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination
              skip={resource.data.skip}
              limit={resource.data.limit}
              total={resource.data.total}
              onChange={setSkip}
            />
          </>
        ) : (
          <EmptyState
            title="No users match"
            description="Change the search or role filter, or create a KANDOR identity."
            icon={<Users className="h-5 w-5" />}
          />
        )}
      </Card>

      <Modal
        open={createOpen}
        title="Create KANDOR user"
        description="Assign the minimum role required. Account creation is audited."
        onClose={() => !submitting && setCreateOpen(false)}
      >
        <form className="space-y-4 p-5" onSubmit={createUser}>
          <div>
            <label className="label" htmlFor="user-email">
              Email address
            </label>
            <Input
              id="user-email"
              type="email"
              autoComplete="off"
              required
              value={form.email}
              onChange={(event) =>
                setForm({ ...form, email: event.target.value })
              }
              placeholder="analyst@example.local"
            />
          </div>
          <div>
            <label className="label" htmlFor="display-name">
              Display name
            </label>
            <Input
              id="display-name"
              required
              minLength={1}
              maxLength={120}
              value={form.display_name}
              onChange={(event) =>
                setForm({ ...form, display_name: event.target.value })
              }
              placeholder="Security Analyst"
            />
          </div>
          <div>
            <label className="label" htmlFor="new-role">
              Role
            </label>
            <Select
              id="new-role"
              value={form.role}
              onChange={(event) =>
                setForm({ ...form, role: event.target.value as Role })
              }
            >
              {ROLES.map((item) => (
                <option key={item} value={item}>
                  {humanize(item)}
                </option>
              ))}
            </Select>
            <p className="mt-1.5 text-[10px] text-slate-600">
              Viewers are read-only. Operators may issue approved tasks.
              Administrators control configuration and identities.
            </p>
          </div>
          <div>
            <label className="label" htmlFor="temporary-password">
              Initial password
            </label>
            <Input
              id="temporary-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              maxLength={128}
              value={form.password}
              onChange={(event) =>
                setForm({ ...form, password: event.target.value })
              }
            />
            <p className="mt-1.5 text-[10px] text-slate-600">
              Use 12–128 characters with upper-case, lower-case, and a number.
              Transmit it through a secure channel.
            </p>
          </div>
          {formError && (
            <p
              className="rounded-lg border border-red-500/20 bg-red-500/[.06] p-3 text-xs text-red-300"
              role="alert"
            >
              {formError}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setCreateOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" loading={submitting}>
              <UserCog className="h-4 w-4" /> Create user
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={Boolean(deleteUser)}
        title="Remove user?"
        description="This action prevents future authentication while retaining audit history."
        onClose={() => setDeleteUser(null)}
      >
        <div className="p-5">
          <p className="text-sm text-slate-400">
            Remove{" "}
            <strong className="text-slate-200">{deleteUser?.email}</strong> from
            KANDOR?
          </p>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setDeleteUser(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              loading={submitting}
              onClick={() => void removeUser()}
            >
              Remove user
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
