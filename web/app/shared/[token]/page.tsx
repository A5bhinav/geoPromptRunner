"use client";

import * as React from "react";
import { SharedReport } from "@/components/shared-report";

/**
 * The link a client actually receives. Presents the token once, then hands over
 * to `/shared/view` — see `SharedReport` for why the URL must stop being the
 * credential on first load.
 */
export default function SharedReportPage({ params }: { params: Promise<{ token: string }> }) {
  const token = React.use(params).token;
  return <SharedReport token={token} />;
}
