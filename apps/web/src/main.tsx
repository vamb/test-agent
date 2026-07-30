import React from "react";
import ReactDOM from "react-dom/client";
import { ConfigProvider, theme } from "antd";
import "antd/dist/reset.css";
import { App } from "./App";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <ConfigProvider
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: "#d8c16a",
          colorBgBase: "#0d1110",
          colorBgContainer: "#121815",
          colorBorder: "#26312b",
          colorText: "#eef0e7",
          colorTextSecondary: "#8e988f",
          borderRadius: 3,
          fontFamily: "\"Aptos\", \"Segoe UI\", \"Microsoft YaHei\", sans-serif",
        },
      }}
      button={{ autoInsertSpace: false }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>,
);
