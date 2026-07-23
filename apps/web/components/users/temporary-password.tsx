"use client";

import { Check, Copy, KeyRound, TriangleAlert } from "lucide-react";
import { useState } from "react";

import type { UserWithTemporaryPassword } from "../../src/lib/api/types";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";

export function TemporaryPassword({
  result,
  onClose,
}: Readonly<{ result: UserWithTemporaryPassword; onClose: () => void }>) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(result.temporary_password);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };

  return (
    <Dialog
      description={`Для ${result.user.full_name} · ${result.user.email}`}
      footer={
        <Button onClick={onClose} type="button">
          Понятно
        </Button>
      }
      onClose={onClose}
      open
      title="Временный пароль"
    >
      <div className="secret-result" role="status">
        <span className="secret-icon" aria-hidden="true">
          <KeyRound size={22} />
        </span>
        <p>
          Передайте пароль сотруднику безопасным способом. После закрытия он
          будет удалён из интерфейса и больше не появится.
        </p>
        <div className="secret-value">
          <code>{result.temporary_password}</code>
          <Button onClick={() => void copy()} type="button" variant="secondary">
            {copied ? <Check size={17} /> : <Copy size={17} />}
            {copied ? "Скопировано" : "Копировать"}
          </Button>
        </div>
        <p className="secret-warning">
          <TriangleAlert size={17} aria-hidden="true" />
          Значение показывается только один раз.
        </p>
      </div>
    </Dialog>
  );
}
