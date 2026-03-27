import React from "react";
import { Route, Routes, Navigate } from "react-router-dom";
import Signup from "./component/signup";
import Login from "./component/login";
import Dashboard from "./component/dashboard";

function App() {
  return (
    <>
      <Routes>
        <Route path="/signup" element={<Signup />} />
        <Route path="/login" element={<Login />} />
        <Route path="/loan-login" element={<Login />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </>
  );
}

export default App;
