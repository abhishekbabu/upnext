import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClientProvider } from "@tanstack/react-query";
import App from "@/App";
import { createQueryClient } from "@/lib/queries";
import "@/index.css";

const client = createQueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={client}>
        <App />
      </QueryClientProvider>
    </BrowserRouter>
  </StrictMode>,
);
