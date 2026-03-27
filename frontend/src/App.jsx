import React from "react";
import { Route, Routes, Navigate } from "react-router-dom";
import Signup from "./component/signup";
import Login from "./component/login"


function App() {
  return (
    <>
      <Routes>
        <Route path="/signup" element={<Signup />} />
        <Route path="/login" element={<Login/>} />
      </Routes>
    </>
  );
}

export default App;
