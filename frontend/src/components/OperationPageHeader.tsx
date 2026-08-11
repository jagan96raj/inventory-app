import { Link } from "react-router-dom";
import { History, Plus } from "lucide-react";
import PageHeader from "./ui/PageHeader";
import Button from "./ui/Button";

type Props = {
  title: string;
  subtitle: string;
  formTo: string;
  historyTo: string;
  mode: "form" | "history";
};

export default function OperationPageHeader({ title, subtitle, formTo, historyTo, mode }: Props) {
  return (
    <PageHeader
      eyebrow={mode === "form" ? "Operations" : "History"}
      title={title}
      subtitle={subtitle}
      actions={
        mode === "form" ? (
          <Link to={historyTo}>
            <Button variant="secondary" leftIcon={<History className="h-4 w-4" />}>
              <span className="sm:hidden">History</span>
              <span className="hidden sm:inline">View history</span>
            </Button>
          </Link>
        ) : (
          <Link to={formTo} className="hidden sm:inline-flex">
            <Button leftIcon={<Plus className="h-4 w-4" />}>New record</Button>
          </Link>
        )
      }
    />
  );
}
