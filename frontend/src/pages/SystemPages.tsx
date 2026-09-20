import { ArrowLeft, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { Button, LogoMark } from "../components/ui";

function SystemPage({
  code,
  title,
  description,
}: {
  code: string;
  title: string;
  description: string;
}) {
  return (
    <main className="grid min-h-[70vh] place-items-center p-6 text-center">
      <div>
        <LogoMark className="mx-auto h-14 w-14" />
        <p className="mt-5 font-mono text-xs tracking-[.2em] text-ashborne-400">
          {code}
        </p>
        <h1 className="mt-2 text-2xl font-semibold text-white">{title}</h1>
        <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
          {description}
        </p>
        <Button
          className="mt-6"
          variant="secondary"
          as-child="true"
          onClick={() => window.history.back()}
        >
          <ArrowLeft className="h-4 w-4" /> Go back
        </Button>
      </div>
    </main>
  );
}

export function UnauthorizedPage() {
  return (
    <SystemPage
      code="403 // ACCESS DENIED"
      title="Insufficient clearance"
      description="Your current ASHBORNE role does not permit access to this control surface. This attempt has not changed any system state."
    />
  );
}

export function NotFoundPage() {
  return (
    <main className="grid min-h-screen place-items-center bg-void p-6 text-center">
      <div>
        <ShieldAlert className="mx-auto h-10 w-10 text-slate-700" />
        <p className="mt-5 font-mono text-xs tracking-[.2em] text-ashborne-400">
          404 // UNKNOWN COORDINATE
        </p>
        <h1 className="mt-2 text-2xl font-semibold text-white">
          Page not found
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          The requested ASHBORNE route does not exist.
        </p>
        <Link to="/dashboard">
          <Button className="mt-6" variant="secondary">
            Return to dashboard
          </Button>
        </Link>
      </div>
    </main>
  );
}
